import os
import json
import re
import socket
import asyncio
import base64
import tempfile
import time
from pathlib import Path
from config import (Config, normalize_mac, _validate_ip, validate_config, derive_subnet_broadcast, SETTINGS_DIR)

_ARP_PATH = Path("/proc/net/arp")

async def _neighbour_mac(ip: str):
    """MAC for ip from the kernel's neighbour cache, or None.

    The cache is populated by ARP even when the PC's firewall drops ICMP, so
    this is a reliable "is it on the LAN" check for Windows PCs.
    """
    _arp = _ARP_PATH
    try:
        import main
        if hasattr(main, "_ARP_PATH"):
            _arp = main._ARP_PATH
    except Exception:
        pass
    try:
        if _arp.exists():
            mac = _find_mac_in_arp(_arp.read_text(errors="ignore"), ip)
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
    _nm = _neighbour_mac
    try:
        import main
        if hasattr(main, "_neighbour_mac"):
            _nm = main._neighbour_mac
    except Exception:
        pass
    try:
        neighbour = await asyncio.wait_for(_nm(cfg.ip), 2.5)
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
    _arp = _ARP_PATH
    try:
        import main
        if hasattr(main, "_ARP_PATH"):
            _arp = main._ARP_PATH
    except Exception:
        pass
    try:
        if _arp.exists():
            mac = _find_mac_in_arp(_arp.read_text(errors="ignore"), ip)
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


__all__ = ['status','preflight','_neighbour_mac', '_parse_arp_table', '_parse_ip_neigh', '_find_mac_in_arp', '_build_nbns_query', '_skip_dns_name', '_parse_nbns_response', '_NbnsProtocol', 'netbios_name', 'reverse_dns_name', 'resolve_hostname', '_find_mac_in_neigh', '_ping_once', 'resolve_mac', 'discover_devices', 'derive_deck_ip']
