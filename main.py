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

SCHEMA_VERSION = 1
last_reset_reason = None

@dataclass
class Config:
    alias: str = ""
    mac: str = ""
    ip: str = ""
    broadcast: str = "255.255.255.255"
    probe_port: int = 445

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
    alias = str(d.get("alias", "")).strip()[:32]
    mac = normalize_mac(d["mac"])
    ip = _validate_ip(d["ip"])
    broadcast = _validate_ip(d.get("broadcast", "255.255.255.255"))
    probe_port = int(d.get("probe_port", 445))
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
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("schema mismatch")
        return validate_config(data)
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

async def status(cfg: Config) -> dict:
    ping_ok = False
    tcp_ok = False
    ping_latency = None
    tcp_latency = None

    async def do_ping():
        nonlocal ping_ok, ping_latency
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1000", cfg.ip,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0:
                ping_ok = True
                ping_latency = int((time.monotonic() - t0) * 1000)
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
    return {"online": False, "method": "none", "latency_ms": None}

def preflight(cfg: Config, deck_ip) -> list:
    problems = []
    if not cfg.mac:
        problems.append("missing MAC address")
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

class Plugin:
    async def main(self):
        pass


plugin = Plugin()
try:
    decky.run(plugin) if hasattr(decky, "run") else None
except NameError:
    pass
