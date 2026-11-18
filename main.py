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

from config import *
from pathlib import Path
_ARP_PATH = Path("/proc/net/arp")

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

from network import *
from shutdown import *
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
