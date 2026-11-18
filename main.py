import os
import json
import re
import socket
import asyncio
import base64
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

try:
    import decky
    SETTINGS_DIR = Path(getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", os.environ.get("DECKY_PLUGIN_SETTINGS_DIR", os.path.expanduser("~/.config/wake-pc"))))
except Exception:
    SETTINGS_DIR = Path(os.environ.get("DECKY_PLUGIN_SETTINGS_DIR", os.path.expanduser("~/.config/wake-pc")))

SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)
_ARP_PATH = Path("/proc/net/arp")
last_reset_reason = None

@dataclass
class Config:
    alias: str = "My PC"
    mac: str = ""
    ip: str = ""
    broadcast: str = "255.255.255.255"
    ssh_user: str = ""

def normalize_mac(mac: str) -> str:
    s = mac.strip().replace("-", "").replace(":", "").replace(".", "")
    if len(s) != 12 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise ValueError("invalid mac")
    s = s.lower()
    return ":".join(s[i:i+2] for i in range(0, 12, 2))

def _validate_ip(v):
    parts = v.split(".")
    if len(parts) != 4:
        raise ValueError("invalid ip")
    for p in parts:
        if not p.isdigit() or not (0 <= int(p) <= 255):
            raise ValueError("invalid ip")
    return v

def validate_config(d: dict) -> Config:
    alias = str(d.get("alias", "My PC")).strip()[:32] or "My PC"
    ip = _validate_ip(str(d.get("ip", "")).strip())
    mac_raw = str(d.get("mac", "")).strip()
    mac = normalize_mac(mac_raw) if mac_raw else ""
    broadcast = _validate_ip(str(d.get("broadcast") or derive_subnet_broadcast(ip) or "255.255.255.255"))
    ssh_user = str(d.get("ssh_user", "") or "").strip()[:64]
    return Config(alias=alias, mac=mac, ip=ip, broadcast=broadcast, ssh_user=ssh_user)

def _config_path():
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return SETTINGS_DIR / "config.json"

def load_config() -> Config:
    global last_reset_reason
    path = _config_path()
    if not path.exists():
        cfg = Config()
        save_config(cfg)
        return cfg
    try:
        data = json.loads(path.read_text())
        version = data.get("schema_version")
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError("schema mismatch")
        cfg = validate_config(data)
        if version != SCHEMA_VERSION:
            save_config(cfg)
        return cfg
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = path.with_name(path.name + f".bak.{ts}")
        try:
            path.rename(backup)
        except Exception:
            pass
        last_reset_reason = str(e) if not isinstance(e, json.JSONDecodeError) else "corrupt json"
        cfg = Config()
        save_config(cfg)
        return cfg

def save_config(cfg: Config) -> None:
    path = _config_path()
    data = asdict(cfg)
    data["schema_version"] = SCHEMA_VERSION
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def reset_config(reason) -> Config:
    global last_reset_reason
    last_reset_reason = reason
    cfg = Config()
    save_config(cfg)
    return cfg


def build_magic_packet(mac: str) -> bytes:
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", "").replace(".", ""))
    return b"\xff" * 6 + mac_bytes * 16

def derive_subnet_broadcast(ip: str):
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return None
        for p in parts:
            if not p.isdigit() or not (0 <= int(p) <= 255):
                return None
    except Exception:
        return None
    return ".".join(parts[:3] + ["255"])

async def wake(cfg: Config) -> dict:
    if not cfg.mac:
        resolved = await resolve_mac(cfg.ip)
        if not resolved:
            return {
                "error": "mac_unknown",
                "message": "MAC address unknown. Turn the PC on once, save again, or use Discover.",
            }
        cfg.mac = resolved
        try:
            save_config(cfg)
        except Exception:
            pass
    mac = cfg.mac
    packet = build_magic_packet(mac)
    destinations = [cfg.broadcast, derive_subnet_broadcast(cfg.ip), cfg.ip]
    destinations = [d for d in destinations if d]
    # unique
    seen = set()
    uniq = []
    for d in destinations:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    sent_to = []
    failed = []
    loop = asyncio.get_event_loop()
    for dest in uniq:
        for port in (9, 7):
            for i in range(3):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    await loop.run_in_executor(None, sock.sendto, packet, (dest, port))
                    sock.close()
                    if dest not in sent_to:
                        sent_to.append(dest)
                except Exception:
                    if dest not in failed:
                        failed.append(dest)
                if i < 2:
                    await asyncio.sleep(0.15)
    return {"mac": mac, "sent_to": sent_to, "failed": failed}

async def _neighbour_mac(ip: str):
    """MAC for ip from the kernel's neighbour cache, or None.

    The cache is populated by ARP even when the PC's firewall drops ICMP, so
    this is a reliable "is it on the LAN" check for Windows PCs.
    """
    try:
        if _ARP_PATH.exists():
            mac = _find_mac_in_arp(_ARP_PATH.read_text(errors="ignore"), ip)
            if mac:
                return mac
    except Exception:
        pass
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "neigh", "show", ip,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), 2.0)
        return _find_mac_in_neigh(out.decode(errors="ignore"), ip)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception:
        return None


async def status(cfg: Config) -> dict:
    ping_ok = False
    ping_latency = None

    async def do_ping():
        nonlocal ping_ok, ping_latency
        t0 = time.monotonic()
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1", cfg.ip,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), 2.5)
            if proc.returncode == 0:
                ping_ok = True
                ping_latency = int((time.monotonic() - t0) * 1000)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            pass

    try:
        await asyncio.wait_for(do_ping(), timeout=4.0)
    except asyncio.TimeoutError:
        pass

    if ping_ok:
        return {"online": True, "method": "ping", "latency_ms": ping_latency}
    try:
        neighbour = await asyncio.wait_for(_neighbour_mac(cfg.ip), 2.5)
    except Exception:
        neighbour = None
    if neighbour:
        return {"online": True, "method": "arp", "latency_ms": None}
    return {"online": False, "method": "none", "latency_ms": None}

def preflight(cfg: Config, deck_ip) -> list:
    problems = []
    if not cfg.mac:
        problems.append("MAC not learned yet — turn the PC on once or use Discover")
    if not cfg.ip:
        problems.append("missing IP address")
    # broadcast validity
    try:
        _validate_ip(cfg.broadcast)
    except Exception:
        problems.append("illegal broadcast address")
    # /24 mismatch warning
    if deck_ip and cfg.ip:
        if cfg.ip.split(".")[:3] != str(deck_ip).split(".")[:3]:
            problems.append("/24 subnet mismatch warning")
    return problems

def _parse_arp_table(text: str, prefix: str) -> list:
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            ip, hw = parts[0], parts[3]
            if ip.startswith(prefix + ".") and hw and hw != "00:00:00:00:00:00":
                out.append({"ip": ip, "mac": hw.lower()})
    return out


def _parse_ip_neigh(text: str, prefix: str) -> list:
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].startswith(prefix + ".") and "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts):
                mac = parts[idx + 1].lower()
                if mac and mac != "00:00:00:00:00:00":
                    out.append({"ip": parts[0], "mac": mac})
    return out


def _find_mac_in_arp(text: str, ip: str):
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == ip and parts[3] != "00:00:00:00:00:00":
            try:
                return normalize_mac(parts[3])
            except ValueError:
                return None
    return None


def _build_nbns_query() -> bytes:
    """Node Status Request for the wildcard name, asking for NetBIOS names."""
    header = b"\x80\x94\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    # NetBIOS name "*" (one byte 0x2A) padded to 16 bytes with zeros, then
    # nibble-encoded with "A".."P".
    qname = b"\x20" + b"CK" + b"A" * 30 + b"\x00"
    return header + qname + b"\x00\x21\x00\x01"


def _skip_dns_name(data: bytes, idx: int) -> int:
    if idx >= len(data):
        raise ValueError("truncated name")
    if data[idx] & 0xC0 == 0xC0:
        if idx + 2 > len(data):
            raise ValueError("truncated pointer")
        return idx + 2
    while idx < len(data):
        length = data[idx]
        if length == 0:
            return idx + 1
        if length & 0xC0:
            raise ValueError("bad label")
        idx += length + 1
    raise ValueError("truncated name")


def _parse_nbns_response(data: bytes):
    """The PC's NetBIOS workstation name from a Node Status Response."""
    try:
        if len(data) < 12:
            return None
        if int.from_bytes(data[2:4], "big") & 0x000F:
            return None
        if int.from_bytes(data[6:8], "big") < 1:
            return None
        idx = _skip_dns_name(data, 12)
        idx += 4  # question type + class
        idx = _skip_dns_name(data, idx)
        if idx + 10 > len(data):
            return None
        rtype = int.from_bytes(data[idx:idx + 2], "big")
        if rtype != 0x0021:
            return None
        rdlength = int.from_bytes(data[idx + 8:idx + 10], "big")
        idx += 10
        if idx + rdlength > len(data) or rdlength < 1:
            return None
        count = data[idx]
        entries = data[idx + 1:idx + 1 + count * 18]
        fallback = None
        for i in range(len(entries) // 18):
            entry = entries[i * 18:(i + 1) * 18]
            suffix = entry[15]
            flags = int.from_bytes(entry[16:18], "big")
            if flags & 0x8000:  # group name, not the machine
                continue
            name = entry[:15].decode("latin-1").strip().strip("\x00").strip()
            if not name or name.upper().startswith("__MSBROWSE__"):
                continue
            if suffix == 0x00:
                return name
            if suffix == 0x20 and fallback is None:
                fallback = name
        return fallback
    except Exception:
        return None


class _NbnsProtocol(asyncio.DatagramProtocol):
    def __init__(self, future):
        self.future = future

    def error_received(self, exc):
        if not self.future.done():
            self.future.set_result(None)

    def datagram_received(self, data, addr):
        if not self.future.done():
            self.future.set_result(data)


async def netbios_name(ip: str):
    """Ask the host for its Windows/NetBIOS name over UDP 137."""
    future = None
    transport = None
    try:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _NbnsProtocol(future), remote_addr=(ip, 137),
        )
        transport.sendto(_build_nbns_query())
        data = await asyncio.wait_for(future, 0.8)
        return _parse_nbns_response(data) if data else None
    except Exception:
        return None
    finally:
        if transport is not None:
            transport.close()


async def reverse_dns_name(ip: str):
    try:
        loop = asyncio.get_running_loop()
        name, _, _ = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip), 0.8,
        )
        name = (name or "").strip().rstrip(".")
        if name and "." not in name:
            return name
        if name:
            return name.split(".")[0]
    except Exception:
        pass
    return None


async def resolve_hostname(ip: str):
    name = await netbios_name(ip)
    if name:
        return name
    return await reverse_dns_name(ip)


def _find_mac_in_neigh(text: str, ip: str):
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == ip and "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts) and parts[idx + 1] != "00:00:00:00:00:00":
                try:
                    return normalize_mac(parts[idx + 1])
                except ValueError:
                    return None
    return None


async def _ping_once(ip: str) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "1", ip,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception:
        return
    try:
        await asyncio.wait_for(proc.wait(), 2.0)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
    except Exception:
        pass


async def resolve_mac(ip: str):
    await _ping_once(ip)
    try:
        if _ARP_PATH.exists():
            mac = _find_mac_in_arp(_ARP_PATH.read_text(errors="ignore"), ip)
            if mac:
                return mac
    except Exception:
        pass
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "neigh", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return _find_mac_in_neigh(out.decode(errors="ignore"), ip)
    except Exception:
        return None


async def discover_devices() -> dict:
    deck_ip = derive_deck_ip()
    if not deck_ip:
        return {"error": "Deck is not on a network"}
    prefix = ".".join(deck_ip.split(".")[:3])

    sem = asyncio.Semaphore(64)

    async def ping_host(i):
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "1", "-W", "1", f"{prefix}.{i}",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), 2.0)
            except Exception:
                pass

    try:
        await asyncio.wait_for(asyncio.gather(*(ping_host(i) for i in range(1, 255))), timeout=12.0)
    except asyncio.TimeoutError:
        pass

    found = {}
    try:
        for d in _parse_arp_table(Path("/proc/net/arp").read_text(), prefix):
            found[d["ip"]] = d
    except Exception:
        pass
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "neigh", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        for d in _parse_ip_neigh(out.decode(errors="ignore"), prefix):
            found[d["ip"]] = d
    except Exception:
        pass

    found.pop(deck_ip, None)
    found.pop(prefix + ".255", None)

    sem = asyncio.Semaphore(32)

    async def add_name(ip):
        async with sem:
            try:
                name = await asyncio.wait_for(resolve_hostname(ip), 2.0)
            except Exception:
                name = None
            if name:
                found[ip]["name"] = name

    try:
        await asyncio.wait_for(asyncio.gather(*(add_name(ip) for ip in found)), timeout=4.0)
    except asyncio.TimeoutError:
        pass

    return {"deck_ip": deck_ip, "devices": [found[ip] for ip in sorted(found, key=lambda s: tuple(map(int, s.split("."))))]}


def derive_deck_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""

def _ssh_key_path() -> Path:
    return SETTINGS_DIR / "shutdown_key"


def _ssh_pub_path() -> Path:
    return SETTINGS_DIR / "shutdown_key.pub"


def _known_hosts_path() -> Path:
    return SETTINGS_DIR / "known_hosts"


def _askpass_path() -> Path:
    return SETTINGS_DIR / "askpass.sh"


def ensure_askpass_helper() -> str:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _askpass_path()
    path.write_text('#!/bin/sh\nprintf \'%s\\n\' "$WAKE_PC_SSH_PASSWORD"\n')
    os.chmod(path, 0o700)
    return str(path)


async def ensure_shutdown_key():
    """Return (private key path, public key line), generating on first use."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    key = _ssh_key_path()
    pub = _ssh_pub_path()
    if not (key.exists() and pub.exists()):
        for path in (key, pub):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "decky-wake-pc",
            "-f", str(key),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore").strip() or "ssh-keygen failed")
        os.chmod(key, 0o600)
        os.chmod(pub, 0o644)
    return str(key), pub.read_text().strip()


def _encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _key_install_script(public_key: str) -> str:
    key = public_key.replace("'", "''")
    return f"""$key = '{key}'
$userKey = Join-Path $env:USERPROFILE '.ssh\\authorized_keys'
New-Item -ItemType Directory -Force -Path (Split-Path $userKey) | Out-Null
if (-not (Test-Path $userKey)) {{ New-Item -ItemType File -Path $userKey | Out-Null }}
if (-not (Select-String -Path $userKey -SimpleMatch $key -Quiet -ErrorAction SilentlyContinue)) {{
  Add-Content -Path $userKey -Value $key
}}
try {{
  $adminKey = Join-Path $env:ProgramData 'ssh\\administrators_authorized_keys'
  New-Item -ItemType Directory -Force -Path (Split-Path $adminKey) | Out-Null
  if (-not (Test-Path $adminKey)) {{ New-Item -ItemType File -Path $adminKey | Out-Null }}
  if (-not (Select-String -Path $adminKey -SimpleMatch $key -Quiet -ErrorAction SilentlyContinue)) {{
    Add-Content -Path $adminKey -Value $key
  }}
  icacls $adminKey /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
}} catch {{ }}
Write-Output 'ok'
"""


def _key_install_remote_command(public_key: str) -> str:
    return "powershell -NoProfile -NonInteractive -EncodedCommand " + _encode_powershell(
        _key_install_script(public_key)
    )


OPENSSH_ENABLE_COMMAND = (
    "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; "
    "Start-Service sshd; "
    "Set-Service -Name sshd -StartupType Automatic; "
    "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' "
    "-Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22"
)

SSH_MESSAGES = {
    "ssh_unavailable": "Cannot reach the PC over SSH. Enable OpenSSH Server on the PC and try again.",
    "auth_failed": "Wrong Windows username or password.",
    "host_key_changed": "The PC's SSH host key changed. Reset the shutdown setup in Settings, then configure again.",
    "timeout": "The PC did not answer in time. Check that it is on and reachable.",
    "key_install_failed": "Connected, but the SSH key could not be installed. Try the setup again.",
    "ssh_error": "The SSH command failed. Check that OpenSSH Server is enabled on the PC.",
    "missing_ip": "Enter the PC IP address in Settings first.",
}


def _ssh_error(stderr: str) -> str:
    s = (stderr or "").lower()
    if "connection refused" in s or "no route to host" in s or "could not resolve" in s:
        return "ssh_unavailable"
    if "permission denied" in s:
        return "auth_failed"
    if "host key verification failed" in s or "remote host identification has changed" in s:
        return "host_key_changed"
    if "timed out" in s or "timeout" in s:
        return "timeout"
    return "ssh_error"


def _ssh_failure(code: str, *, command: str = "", detail: str = "") -> dict:
    message = SSH_MESSAGES.get(code, SSH_MESSAGES["ssh_error"])
    if code == "key_install_failed" and detail:
        message = f"{message} ({detail})"
    out = {"error": code, "message": message}
    if command:
        out["command"] = command
    return out


def _ssh_base_args(user: str, ip: str) -> list:
    return [
        "ssh", "-F", "/dev/null",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={_known_hosts_path()}",
        "-o", "ConnectTimeout=8",
        "-o", "LogLevel=ERROR",
        "-l", user, ip,
    ]


async def _run_ssh(args: list, env=None, timeout: float = 30.0):
    """Run ssh and always return (returncode|None, stdout, stderr)."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")
    except asyncio.TimeoutError:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return None, "", "timed out"
    except Exception as e:
        return None, "", str(e)


def _user_candidates(user: str) -> list:
    out = [user]
    if "\\" in user:
        bare = user.rsplit("\\", 1)[1].strip()
        if bare and bare not in out:
            out.append(bare)
    return out


async def configure_shutdown(user: str, password: str) -> dict:
    user = (user or "").strip()[:64]
    if not user or not password:
        return {"error": "invalid_credentials", "message": "Enter the Windows username and password."}
    cfg = load_config()
    if not cfg.ip:
        return _ssh_failure("missing_ip")
    try:
        key_path, public_key = await ensure_shutdown_key()
    except Exception as e:
        return {"error": "key_generation_failed", "message": str(e)}
    askpass = ensure_askpass_helper()
    remote = _key_install_remote_command(public_key)
    fallback_command = remote

    env = os.environ.copy()
    env.update({
        "WAKE_PC_SSH_PASSWORD": password,
        "SSH_ASKPASS": askpass,
        "SSH_ASKPASS_REQUIRE": "force",
        "DISPLAY": env.get("DISPLAY", ":0"),
    })

    last_code = "ssh_error"
    last_detail = ""
    working_user = ""
    for candidate in _user_candidates(user):
        args = _ssh_base_args(candidate, cfg.ip) + [
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "PubkeyAuthentication=no",
            remote,
        ]
        code, _, err = await _run_ssh(args, env=env, timeout=30.0)
        if code == 0:
            working_user = candidate
            break
        last_code = "timeout" if code is None else _ssh_error(err)
        last_detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else ""
        if last_code == "auth_failed":
            continue
        break

    if not working_user:
        command = OPENSSH_ENABLE_COMMAND if last_code == "ssh_unavailable" else ""
        return _ssh_failure(last_code, command=command, detail=last_detail)

    verify_args = _ssh_base_args(working_user, cfg.ip) + [
        "-i", key_path,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "cmd", "/c", "echo", "ok",
    ]
    code, _, err = await _run_ssh(verify_args, timeout=15.0)
    if code != 0:
        mapped = "timeout" if code is None else _ssh_error(err)
        detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else ""
        failure = mapped if mapped in ("host_key_changed", "timeout") else "key_install_failed"
        return _ssh_failure(failure, command=fallback_command, detail=detail)

    cfg.ssh_user = working_user
    save_config(cfg)
    return {"ok": True, "user": working_user}


async def shutdown_pc(cfg: Config) -> dict:
    if not cfg.ssh_user:
        return {
            "error": "shutdown_not_configured",
            "message": "Configure shutdown in Settings first.",
        }
    key_path = _ssh_key_path()
    if not key_path.exists():
        return {
            "error": "shutdown_not_configured",
            "message": "The shutdown key is missing. Configure shutdown again in Settings.",
        }
    args = _ssh_base_args(cfg.ssh_user, cfg.ip) + [
        "-i", str(key_path),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "shutdown", "/s", "/t", "0",
    ]
    code, _, err = await _run_ssh(args, timeout=15.0)
    if code == 0:
        return {"ok": True}
    detail = (err or "").strip().lower()
    # Windows may drop the SSH connection as it shuts down, before ssh can
    # report the remote exit status. Treat that specific case as success.
    if code == 255 and (not detail or "connection closed" in detail or "broken pipe" in detail or "reset by peer" in detail):
        return {"ok": True, "connection_closed": True}
    mapped = "timeout" if code is None else _ssh_error(err)
    return _ssh_failure(mapped, detail=(err or "").strip().splitlines()[-1] if (err or "").strip() else "")


async def reset_shutdown_setup() -> dict:
    try:
        cfg = load_config()
        cfg.ssh_user = ""
        save_config(cfg)
        for path in (_ssh_key_path(), _ssh_pub_path(), _known_hosts_path(), _askpass_path()):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


class Plugin:
    async def main(self):
        pass

    async def get_config(self):
        try:
            cfg = load_config()
            return {"config": asdict(cfg)}
        except Exception as e:
            return {"error": str(e)}

    async def save_config(self, data):
        try:
            data = dict(data or {})
            existing = load_config()
            # ssh_user is backend-owned: keep it when the form does not include
            # it, and never let a client mark shutdown configured without a key.
            if not data.get("ssh_user") and existing.ssh_user and _ssh_key_path().exists():
                data["ssh_user"] = existing.ssh_user
            if data.get("ssh_user") and not _ssh_key_path().exists():
                data["ssh_user"] = ""
            cfg = validate_config(data)
            if not cfg.mac:
                mac = await resolve_mac(cfg.ip)
                if mac:
                    cfg.mac = mac
            save_config(cfg)
            return {"ok": True, "config": asdict(cfg), "mac_resolved": bool(cfg.mac)}
        except Exception as e:
            return {"error": str(e)}

    async def learn_mac(self):
        try:
            cfg = load_config()
            mac = await resolve_mac(cfg.ip)
            if mac:
                cfg.mac = mac
                save_config(cfg)
            return {"mac": mac}
        except Exception as e:
            return {"error": str(e)}

    async def wake(self):
        try:
            cfg = load_config()
            return await wake(cfg)
        except Exception as e:
            return {"error": str(e)}

    async def status(self):
        try:
            cfg = load_config()
            return await status(cfg)
        except Exception as e:
            return {"error": str(e)}

    async def preflight(self):
        try:
            cfg = load_config()
            deck_ip = derive_deck_ip()
            return {"problems": preflight(cfg, deck_ip), "deck_ip": deck_ip}
        except Exception as e:
            return {"error": str(e)}

    async def discover(self):
        try:
            return await discover_devices()
        except Exception as e:
            return {"error": str(e)}

    async def configure_shutdown(self, user, password):
        try:
            return await configure_shutdown(user, password)
        except Exception as e:
            return {"error": str(e)}

    async def shutdown(self):
        try:
            cfg = load_config()
            return await shutdown_pc(cfg)
        except Exception as e:
            return {"error": str(e)}

    async def reset_shutdown_setup(self):
        try:
            return await reset_shutdown_setup()
        except Exception as e:
            return {"error": str(e)}

plugin = Plugin()
try:
    decky.run(plugin) if hasattr(decky, "run") else None
except NameError:
    pass
