from backend.src.config import *
from backend.src.network import *
from backend.src.shutdown import *
from backend.src.wake import *
import backend.src.config as _c
# expose module-level private names tests expect
import backend.src.network as _n
import backend.src.shutdown as _s
import backend.src.wake as _w
for _m in (_c, _n, _s, _w):
    for _k, _v in vars(_m).items():
        globals()[_k] = _v
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
