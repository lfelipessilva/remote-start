import os
import json
import re
import tempfile
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


class Plugin:
    async def main(self):
        pass


plugin = Plugin()
try:
    decky.run(plugin) if hasattr(decky, "run") else None
except NameError:
    pass
