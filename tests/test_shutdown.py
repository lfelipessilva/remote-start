import base64
from unittest import mock

import pytest

import main


def _proc(code=0, out=b"", err=b""):
    proc = mock.MagicMock()
    proc.returncode = code
    proc.communicate = mock.AsyncMock(return_value=(out, err))
    return proc


def _exec_factory(procs):
    calls = []
    queue = list(procs)

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return queue.pop(0)

    return fake_exec, calls


def test_key_install_script_contains_key_and_acl_sids():
    script = main._key_install_script("ssh-ed25519 AAAA test")
    assert "ssh-ed25519 AAAA test" in script
    assert "administrators_authorized_keys" in script
    assert "*S-1-5-32-544" in script
    assert "*S-1-5-18" in script


def test_encode_powershell_round_trips():
    script = "Write-Output 'ok'"
    encoded = main._encode_powershell(script)
    assert base64.b64decode(encoded).decode("utf-16le") == script


@pytest.mark.asyncio
async def test_ensure_shutdown_key_reuses_existing(tmp_path):
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    (tmp_path / "shutdown_key.pub").write_text("ssh-ed25519 AAAA\n")
    key, pub = await main.ensure_shutdown_key()
    assert key == str(tmp_path / "shutdown_key")
    assert pub == "ssh-ed25519 AAAA"


def test_ssh_error_mapping():
    assert main._ssh_error("ssh: connect to host 1.2.3.4 port 22: Connection refused") == "ssh_unavailable"
    assert main._ssh_error("Permission denied (publickey,password).") == "auth_failed"
    assert main._ssh_error("Host key verification failed.") == "host_key_changed"
    assert main._ssh_error("Connection timed out") == "timeout"
    assert main._ssh_error("something else") == "ssh_error"


def test_user_candidates():
    assert main._user_candidates("Luis") == ["Luis"]
    assert main._user_candidates("DESKTOP\\Luis") == ["DESKTOP\\Luis", "Luis"]


@pytest.mark.asyncio
async def test_configure_shutdown_installs_key_and_saves_user(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42"))

    async def fake_key():
        return str(tmp_path / "shutdown_key"), "ssh-ed25519 AAAA test"

    monkeypatch.setattr(main, "ensure_shutdown_key", fake_key)
    monkeypatch.setattr(main, "ensure_askpass_helper", lambda: "/tmp/askpass.sh")
    fake_exec, calls = _exec_factory([_proc(0, b"ok"), _proc(0, b"ok\n")])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.configure_shutdown("Luis", "s3cret")

    assert res == {"ok": True, "user": "Luis"}
    assert main.load_config().ssh_user == "Luis"
    assert all("s3cret" not in " ".join(map(str, args)) for args, _ in calls)
    assert calls[0][1]["env"]["WAKE_PC_SSH_PASSWORD"] == "s3cret"
    assert "BatchMode=yes" in calls[1][0]
    assert str(tmp_path / "known_hosts") in " ".join(calls[1][0])


@pytest.mark.asyncio
async def test_configure_shutdown_reports_bad_password_and_does_not_save(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42"))

    async def fake_key():
        return str(tmp_path / "shutdown_key"), "ssh-ed25519 AAAA test"

    monkeypatch.setattr(main, "ensure_shutdown_key", fake_key)
    monkeypatch.setattr(main, "ensure_askpass_helper", lambda: "/tmp/askpass.sh")
    fake_exec, _ = _exec_factory([_proc(255, b"", b"Permission denied (publickey,password).")])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.configure_shutdown("Luis", "wrong")
    assert res["error"] == "auth_failed"
    assert main.load_config().ssh_user == ""
    assert "command" not in res


@pytest.mark.asyncio
async def test_configure_shutdown_reports_enable_command_when_ssh_is_off(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42"))

    async def fake_key():
        return str(tmp_path / "shutdown_key"), "ssh-ed25519 AAAA test"

    monkeypatch.setattr(main, "ensure_shutdown_key", fake_key)
    monkeypatch.setattr(main, "ensure_askpass_helper", lambda: "/tmp/askpass.sh")
    fake_exec, _ = _exec_factory([_proc(255, b"", b"ssh: connect to host 192.168.1.42 port 22: Connection refused")])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.configure_shutdown("Luis", "s3cret")
    assert res["error"] == "ssh_unavailable"
    assert "Add-WindowsCapability" in res["command"]


@pytest.mark.asyncio
async def test_configure_shutdown_reports_key_install_failure(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42"))

    async def fake_key():
        return str(tmp_path / "shutdown_key"), "ssh-ed25519 AAAA test"

    monkeypatch.setattr(main, "ensure_shutdown_key", fake_key)
    monkeypatch.setattr(main, "ensure_askpass_helper", lambda: "/tmp/askpass.sh")
    fake_exec, _ = _exec_factory([
        _proc(0, b"ok"),
        _proc(255, b"", b"Permission denied (publickey)."),
    ])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.configure_shutdown("Luis", "s3cret")
    assert res["error"] == "key_install_failed"
    assert main.load_config().ssh_user == ""


@pytest.mark.asyncio
async def test_shutdown_requires_ssh_user():
    res = await main.shutdown_pc(main.Config(ip="192.168.1.42"))
    assert res["error"] == "shutdown_not_configured"


@pytest.mark.asyncio
async def test_shutdown_runs_key_only_ssh(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    fake_exec, calls = _exec_factory([_proc(0)])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.shutdown_pc(main.Config(ip="192.168.1.42", ssh_user="Luis"))

    assert res == {"ok": True}
    assert "BatchMode=yes" in calls[0][0]
    assert "shutdown" in calls[0][0]
    assert str(tmp_path / "known_hosts") in " ".join(calls[0][0])


@pytest.mark.asyncio
async def test_shutdown_treats_closed_connection_as_success(tmp_path, monkeypatch):
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    fake_exec, _ = _exec_factory([_proc(255, b"", b"Connection closed by 192.168.1.42")])
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    res = await main.shutdown_pc(main.Config(ip="192.168.1.42", ssh_user="Luis"))
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_save_config_preserves_ssh_user_when_key_exists(tmp_path):
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    main.save_config(main.Config(ip="192.168.1.42", ssh_user="Luis"))

    res = await main.Plugin().save_config({
        "ip": "192.168.1.42", "alias": "My PC", "mac": "aa:bb:cc:dd:ee:ff",
        "broadcast": "",
    })
    assert res["config"]["ssh_user"] == "Luis"


@pytest.mark.asyncio
async def test_save_config_refuses_ssh_user_without_key(tmp_path):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42"))

    res = await main.Plugin().save_config({
        "ip": "192.168.1.42", "alias": "My PC", "mac": "aa:bb:cc:dd:ee:ff",
        "broadcast": "", "ssh_user": "Luis",
    })
    assert res["config"]["ssh_user"] == ""


@pytest.mark.asyncio
async def test_reset_shutdown_setup_clears_user_and_files(tmp_path):
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42", ssh_user="Luis"))
    for name in ("shutdown_key", "shutdown_key.pub", "known_hosts", "askpass.sh"):
        (tmp_path / name).write_text("x")

    res = await main.reset_shutdown_setup()

    assert res == {"ok": True}
    assert main.load_config().ssh_user == ""
    assert not any((tmp_path / name).exists() for name in
                   ("shutdown_key", "shutdown_key.pub", "known_hosts", "askpass.sh"))
