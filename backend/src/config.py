import os
import json
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

try:
    import decky
    SETTINGS_DIR = Path(getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", os.environ.get("DECKY_PLUGIN_SETTINGS_DIR", os.path.expanduser("~/.config/remote-start"))))
except Exception:
    SETTINGS_DIR = Path(os.environ.get("DECKY_PLUGIN_SETTINGS_DIR", os.path.expanduser("~/.config/remote-start")))

SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)

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

def validate_config(d: dict) -> Config:
    alias = str(d.get("alias", "My PC")).strip()[:32] or "My PC"
    ip = _validate_ip(str(d.get("ip", "")).strip())
    mac_raw = str(d.get("mac", "")).strip()
    mac = normalize_mac(mac_raw) if mac_raw else ""
    broadcast = _validate_ip(str(d.get("broadcast") or derive_subnet_broadcast(ip) or "255.255.255.255"))
    ssh_user = str(d.get("ssh_user", "") or "").strip()[:64]
    return Config(alias=alias, mac=mac, ip=ip, broadcast=broadcast, ssh_user=ssh_user)

def _settings_dir():
    try:
        import main
        if hasattr(main, "SETTINGS_DIR"):
            return main.SETTINGS_DIR
    except Exception:
        pass
    return SETTINGS_DIR

def _config_path():
    d = _settings_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"

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

last_reset_reason = None
