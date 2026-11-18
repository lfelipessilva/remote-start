from main import _parse_arp_table, _parse_ip_neigh

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
