import pytest
from unittest import mock
from main import build_magic_packet, derive_subnet_broadcast, wake, Config

def test_magic_packet_size_and_bytes():
    p = build_magic_packet("aa:bb:cc:dd:ee:ff")
    assert len(p) == 102
    assert p[:6] == b"\xff"*6
    assert p[6:] == bytes.fromhex("aabbccddeeff") * 16

def test_derive_subnet_broadcast():
    assert derive_subnet_broadcast("192.168.1.42") == "192.168.1.255"
    assert derive_subnet_broadcast("not an ip") is None
    assert derive_subnet_broadcast("999.1.1.1") is None

@pytest.mark.asyncio
async def test_wake_fanout():
    cfg = Config(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.42", broadcast="255.255.255.255")
    fake_sock = mock.MagicMock()
    with mock.patch("main.socket.socket", return_value=fake_sock):
        res = await wake(cfg)
    assert res["mac"] == "aa:bb:cc:dd:ee:ff"
    assert set(res["sent_to"]) == {"255.255.255.255", "192.168.1.255", "192.168.1.42"}
    # 3 dests * 2 ports * 3 rounds = 18 sends
    assert fake_sock.sendto.call_count == 18