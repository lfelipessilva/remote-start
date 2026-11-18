"""Load main.py the way Decky does.

Decky loads the backend with ``spec_from_file_location("_", main.py)`` from a
different working directory and only adds ``<plugin>/py_modules`` to
``sys.path``. The plugin directory itself is not importable, so imports like
``from backend.src.config import ...`` only work if main.py adds it.
"""

import os
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]

LOADER_SCRIPT = """
import asyncio
import json
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location

decky = types.ModuleType("decky")
decky.DECKY_PLUGIN_SETTINGS_DIR = sys.argv[2]
sys.modules["decky"] = decky

spec = spec_from_file_location("_", sys.argv[1])
module = module_from_spec(spec)
spec.loader.exec_module(module)

result = asyncio.run(module.Plugin().save_config({"alias": "Test PC", "ip": "127.0.0.1"}))
print(json.dumps(result))
"""


def test_main_loads_and_saves_when_plugin_dir_is_not_on_sys_path(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            LOADER_SCRIPT,
            str(PLUGIN_DIR / "main.py"),
            str(tmp_path),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, proc.stderr
    result = __import__("json").loads(proc.stdout.strip().splitlines()[-1])
    assert result.get("ok") is True, result
    saved = (tmp_path / "config.json").read_text()
    assert '"ip": "127.0.0.1"' in saved
