import asyncio
from unittest import mock
import pytest
from main import Config, status, preflight

@pytest.mark.asyncio
async def test_status_ping_success():
    cfg = Config(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.42", probe_port=445)
    fake_proc = mock.MagicMock()
    fake_proc.returncode = 0
    async def wait(): return 0
    fake_proc.wait = wait
    with mock.patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        res = await status(cfg)
    assert res["online"] is True
    assert res["method"] == "ping"
    assert isinstance(res["latency_ms"], int)

@pytest.mark.asyncio
async def test_status_tcp_fallback():
    cfg = Config(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.42", probe_port=445)
    fake_proc = mock.MagicMock()
    fake_proc.returncode = 1
    async def wait(): return 1
    fake_proc.wait = wait
    # open_connection succeeds
    async def open_conn(host, port): 
        w = mock.MagicMock()
        async def wc(): pass
        w.wait_closed = wc
        return (mock.MagicMock(), w)
    with mock.patch("asyncio.create_subprocess_exec", return_value=fake_proc), \
         mock.patch("asyncio.open_connection", side_effect=open_conn):
        res = await status(cfg)
    assert res["online"] is True
    assert res["method"] == "tcp"

@pytest.mark.asyncio
async def test_status_offline():
    cfg = Config(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.42", probe_port=445)
    fake_proc = mock.MagicMock()
    fake_proc.returncode = 1
    async def wait(): return 1
    fake_proc.wait = wait
    async def open_conn(host, port): raise OSError("nope")
    with mock.patch("asyncio.create_subprocess_exec", return_value=fake_proc), \
         mock.patch("asyncio.open_connection", side_effect=open_conn):
        res = await status(cfg)
    assert res["online"] is False
    assert res["method"] == "none"
    assert res["latency_ms"] is None

def test_preflight():
    cfg = Config(mac="", ip="", broadcast="999.1.1.1", probe_port=445)
    probs = preflight(cfg, "10.0.0.5")
    joined = " ".join(probs).lower()
    assert "mac" in joined
    assert "ip" in joined
    assert "broadcast" in joined
    # /24 mismatch
    cfg2 = Config(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.42", broadcast="192.168.1.255", probe_port=445)
    probs2 = preflight(cfg2, "10.0.0.5")
    joined2 = " ".join(probs2).lower()
    assert "24" in joined2 or "subnet" in joined2 or "mismatch" in joined2
