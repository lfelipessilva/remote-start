import decky


class Plugin:
    async def main(self):
        pass

    async def get_config(self):
        return {}

    async def save_config(self, cfg):
        return {"ok": True}

    async def wake(self):
        return {"ok": True}

    async def status(self):
        return {"online": False, "method": "none", "latency_ms": None}

    async def preflight(self):
        return []

    async def test_wake(self):
        return {"ok": True}

    async def test_probe(self):
        return {"ok": True}

    async def get_diagnostics(self):
        return []


plugin = Plugin()
async def _main():
    await plugin.main()
decky.run(plugin) if hasattr(decky, "run") else None