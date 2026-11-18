import pytest
from unittest import mock
from main import _find_mac_in_arp, _find_mac_in_neigh, resolve_mac, wake, Config

ARP = """IP address       HW type     Flags       HW address            Mask
192.168.1.42     0x1         0x2         aa:bb:cc:dd:ee:ff     *
192.168.1.43     0x1         0x2         11:22:33:44:55:66     *"""

NEIGH = """192.168.1.42 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.168.1.43 dev wlan0 lladdr 11:22:33:44:55:66 STALE"""


def test_find_mac_in_arp_exact_ip():
    assert _find_mac_in_arp(ARP, "192.168.1.42") == "aa:bb:cc:dd:ee:ff"
    assert _find_mac_in_arp(ARP, "192.168.1.99") is None


def test_find_mac_in_neigh_exact_ip():
    assert _find_mac_in_neigh(NEIGH, "192.168.1.42") == "aa:bb:cc:dd:ee:ff"
    assert _find_mac_in_neigh(NEIGH, "192.168.1.99") is None


@pytest.mark.asyncio
async def test_resolve_mac_reads_arp(tmp_path, monkeypatch):
    import main
    arp = tmp_path / "arp"
    arp.write_text(ARP)

    async def no_ping(*a, **k):
        raise OSError("no ping")

    monkeypatch.setattr(main, "_ARP_PATH", arp)
    with mock.patch("asyncio.create_subprocess_exec", side_effect=no_ping):
        assert await resolve_mac("192.168.1.42") == "aa:bb:cc:dd:ee:ff"


@pytest.mark.asyncio
async def test_wake_without_mac_returns_mac_unknown(monkeypatch):
    import main

    async def none(ip):
        return None

    monkeypatch.setattr(main, "resolve_mac", none)
    with mock.patch("main.socket.socket") as sock:
        res = await wake(Config(ip="192.168.1.42", broadcast="192.168.1.255"))
    assert res["error"] == "mac_unknown"
    assert "Turn the PC on once" in res["message"]
    sock.assert_not_called()


@pytest.mark.asyncio
async def test_save_ip_only_without_mac(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path

    async def none(ip):
        return None

    monkeypatch.setattr(main, "resolve_mac", none)
    res = await main.Plugin().save_config({"ip": "192.168.1.42"})
    assert res["ok"] is True
    assert res["config"]["mac"] == ""
    assert res["mac_resolved"] is False


@pytest.mark.asyncio
async def test_test_wake_reports_mac_unknown(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path

    async def none(ip):
        return None

    monkeypatch.setattr(main, "resolve_mac", none)
    main.save_config(main.Config(ip="192.168.1.42", broadcast="192.168.1.255"))
    res = await main.Plugin().test_wake()
    assert res["error"] == "mac_unknown"
    assert "Turn the PC on once" in res["message"]


@pytest.mark.asyncio
async def test_ping_uses_short_deadline_and_kills_on_timeout(monkeypatch):
    import main
    fake = mock.MagicMock()
    fake.wait = mock.AsyncMock()
    fake.kill = mock.MagicMock()

    async def boom(coro, timeout):
        coro.close()
        raise main.asyncio.TimeoutError()

    with mock.patch("asyncio.create_subprocess_exec", mock.AsyncMock(return_value=fake)) as ex, \
         mock.patch.object(main.asyncio, "wait_for", boom):
        await main._ping_once("192.168.1.42")

    args = ex.call_args[0]
    assert args[0] == "ping" and args[3] == "-W" and args[4] == "1"
    fake.kill.assert_called_once()
