import os
import json
import re
import socket
import asyncio
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

SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
_ARP_PATH = Path("/proc/net/arp")
last_reset_reason = None

@dataclass
class Config:
    alias: str = "My PC"
    mac: str = ""
    ip: str = ""
    broadcast: str = "255.255.255.255"
    probe_port: int = 0

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
    probe_port = int(d.get("probe_port", 0))
    return Config(alias=alias, mac=mac, ip=ip, broadcast=broadcast, probe_port=probe_port)

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
    tcp_ok = False
    ping_latency = None
    tcp_latency = None

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

    async def do_tcp():
        nonlocal tcp_ok, tcp_latency
        if not cfg.probe_port:
            return
        t0 = time.monotonic()
        try:
            reader, writer = await asyncio.open_connection(cfg.ip, cfg.probe_port)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            tcp_ok = True
            tcp_latency = int((time.monotonic() - t0) * 1000)
        except Exception:
            pass

    try:
        await asyncio.wait_for(asyncio.gather(do_ping(), do_tcp()), timeout=4.0)
    except asyncio.TimeoutError:
        pass

    if ping_ok:
        return {"online": True, "method": "ping", "latency_ms": ping_latency}
    if tcp_ok:
        return {"online": True, "method": "tcp", "latency_ms": tcp_latency}
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

_DIAG = []
def record_diag(entry):
    _DIAG.append(entry)
    if len(_DIAG) > 20:
        del _DIAG[:len(_DIAG)-20]

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
            cfg = validate_config(data or {})
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
            res = await wake(cfg)
            record_diag({"ts": datetime.now().isoformat(), "op": "wake", **res})
            return res
        except Exception as e:
            return {"error": str(e)}

    async def status(self):
        try:
            cfg = load_config()
            res = await status(cfg)
            record_diag({"ts": datetime.now().isoformat(), "op": "status", **res})
            return res
        except Exception as e:
            return {"error": str(e)}

    async def preflight(self):
        try:
            cfg = load_config()
            deck_ip = derive_deck_ip()
            return {"problems": preflight(cfg, deck_ip), "deck_ip": deck_ip}
        except Exception as e:
            return {"error": str(e)}

    async def test_wake(self):
        try:
            cfg = load_config()
            res = await wake(cfg)
            if res.get("error"):
                return {"error": res["error"], "message": res.get("message")}
            return {"rounds": 1, "destinations": res.get("sent_to", []), "failed": res.get("failed", [])}
        except Exception as e:
            return {"error": str(e)}

    async def test_probe(self):
        try:
            cfg = load_config()
            t0 = time.monotonic()
            res = await status(cfg)
            res = dict(res)
            res["latency_ms"] = res.get("latency_ms")
            return {"method": res.get("method"), "latency_ms": res.get("latency_ms"), "online": res.get("online")}
        except Exception as e:
            return {"error": str(e)}

    async def discover(self):
        try:
            res = await discover_devices()
            record_diag({"ts": datetime.now().isoformat(), "op": "discover", "count": len(res.get("devices", []))})
            return res
        except Exception as e:
            return {"error": str(e)}

    async def get_diagnostics(self):
        try:
            return {"entries": list(_DIAG)}
        except Exception as e:
            return {"error": str(e)}

plugin = Plugin()
try:
    decky.run(plugin) if hasattr(decky, "run") else None
except NameError:
    pass
