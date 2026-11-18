import struct

from main import _parse_arp_table, _parse_ip_neigh, _parse_nbns_response, _build_nbns_query


def _nbns_response(names):
    header = b"\x80\x94\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00"
    qname = b"\x20" + b"CK" + b"A" * 30 + b"\x00"
    question = qname + b"\x00\x21\x00\x01"
    entries = b""
    for name, suffix, flags in names:
        entries += name.encode().ljust(15, b" ")[:15] + bytes([suffix]) + struct.pack(">H", flags)
    rdata = bytes([len(names)]) + entries
    answer = b"\xc0\x0c" + b"\x00\x21\x00\x01" + b"\x00\x00\x00\x00" + struct.pack(">H", len(rdata)) + rdata
    return header + question + answer

ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         aa:bb:cc:dd:ee:01     *        wlan0
192.168.1.42     0x1         0x2         aa:bb:cc:dd:ee:42     *        wlan0
192.168.1.77     0x1         0x0         00:00:00:00:00:00     *        wlan0
10.0.0.5         0x1         0x2         aa:bb:cc:dd:ee:05     *        eth0
"""

NEIGH = """192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:01 REACHABLE
192.168.1.42 dev wlan0 lladdr aa:bb:cc:dd:ee:42 STALE
192.168.1.50 dev wlan0 FAILED
192.168.1.255 dev wlan0 lladdr ff:ff:ff:ff:ff:ff REACHABLE
"""


def test_parse_arp_filters_prefix_and_incomplete():
    out = _parse_arp_table(ARP, "192.168.1")
    assert out == [
        {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:01"},
        {"ip": "192.168.1.42", "mac": "aa:bb:cc:dd:ee:42"},
    ]


def test_parse_ip_neigh():
    out = _parse_ip_neigh(NEIGH, "192.168.1")
    ips = [d["ip"] for d in out]
    assert "192.168.1.1" in ips
    assert "192.168.1.42" in ips
    assert "192.168.1.50" not in ips
    assert all(d["mac"] != "00:00:00:00:00:00" for d in out)


def test_nbns_query_is_well_formed():
    q = _build_nbns_query()
    assert len(q) == 50
    assert q[2:4] == b"\x00\x00"
    assert q[12:14] == b"\x20C"


def test_parse_nbns_prefers_unique_workstation_name():
    data = _nbns_response([
        ("DESKTOP-GROUP", 0x00, 0x8000),
        ("__MSBROWSE__", 0x01, 0x8000),
        ("GAMING-PC", 0x00, 0x0400),
    ])
    assert _parse_nbns_response(data) == "GAMING-PC"


def test_parse_nbns_falls_back_to_file_server_name():
    data = _nbns_response([
        ("WORKGROUP", 0x00, 0x8000),
        ("BATTLE-STATION", 0x20, 0x0400),
    ])
    assert _parse_nbns_response(data) == "BATTLE-STATION"


def test_parse_nbns_rejects_truncated_and_error_responses():
    assert _parse_nbns_response(b"") is None
    assert _parse_nbns_response(b"\x80\x94\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00") is None
