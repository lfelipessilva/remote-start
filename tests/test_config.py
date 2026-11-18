import os
import json
import pytest
from main import normalize_mac, validate_config, load_config, save_config, reset_config, Config

def test_normalize_mac_colon():
    assert normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"

def test_normalize_mac_raw():
    assert normalize_mac("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"

def test_normalize_mac_dash():
    assert normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"

def test_invalid_mac_raises():
    with pytest.raises(ValueError):
        normalize_mac("zz:bb:cc:dd:ee:ff")

def test_invalid_ip_raises():
    with pytest.raises(ValueError):
        validate_config({"alias":"a","mac":"aa:bb:cc:dd:ee:ff","ip":"999.1.1.1"})

def test_alias_trim_cap():
    cfg = validate_config({"alias":"  " + "x"*40 + "  ","mac":"aa:bb:cc:dd:ee:ff","ip":"1.1.1.1"})
    assert len(cfg.alias) == 32

def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    import main
    main.SETTINGS_DIR = tmp_path
    cfg = Config(alias="pc", mac="aa:bb:cc:dd:ee:ff", ip="10.0.0.5")
    save_config(cfg)
    loaded = load_config()
    assert loaded.alias == "pc"
    assert loaded.mac == "aa:bb:cc:dd:ee:ff"

def test_corrupt_config_resets(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    import main
    main.SETTINGS_DIR = tmp_path
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "config.json").write_text("{bad")
    cfg = load_config()
    assert cfg == Config()
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 1

def test_schema_version_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    import main
    main.SETTINGS_DIR = tmp_path
    save_config(Config())
    data = json.loads((tmp_path/"config.json").read_text())
    assert data["schema_version"] == 1
