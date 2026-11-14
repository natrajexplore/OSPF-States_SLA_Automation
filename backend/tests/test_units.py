"""Pure helpers: hostname guard, retry, IOS error detection, monitor parsers, IOS config parsing."""
import pytest

from app import devices, monitor
from app.inventory import Device
from app.sim.iosconfig import ifname, parse_config


def _dev(name="R4"):
    return Device(name=name, role="x", mgmt_ip="192.168.99.14", router_id="10.255.0.4", username="u", password="p", secret="s")


def test_hostname_guard():
    devices.check_hostname(_dev(), "R4#")
    devices.check_hostname(_dev(), "r4(config-if)#")
    with pytest.raises(devices.HostnameMismatch):
        devices.check_hostname(_dev(), "R7#")


def test_retry():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise OSError("refused")
        return "ok"

    assert devices.retry(flaky, 3, delay=0) == "ok" and len(calls) == 2
    with pytest.raises(OSError):
        devices.retry(lambda: (_ for _ in ()).throw(OSError("x")), 2, delay=0)


def test_ios_errors():
    out = "R4(config-if)#ip ospf bfd\n                   ^\n% Invalid input detected at '^' marker.\n\nR4(config-if)#end"
    errs = devices.ios_errors(out)
    assert len(errs) == 1 and "ip ospf bfd" in errs[0]
    assert devices.ios_errors("R4(config)#router ospf 1\nR4(config-router)#end") == []


def test_neighbor_parser_msec_dead_time():
    out = ("Neighbor ID     Pri   State           Dead Time   Address         Interface\n"
           "10.255.0.4        0   FULL/  -        840 msec    10.1.34.2       Ethernet1/1\n"
           "10.255.0.2       50   FULL/BDR        00:00:37    10.0.123.2      Ethernet1/0\n")
    nb = monitor.parse_neighbors(out)
    assert [n["neighbor"] for n in nb] == ["10.255.0.4", "10.255.0.2"] and all(n["full"] for n in nb)


def test_route_parser_counts_default():
    out = "O*IA  0.0.0.0/0 [110/11] via 10.1.34.1\nO IA     10.0.123.0/24 [110/20] via 10.1.34.1\nO E2     172.16.99.0"
    assert monitor.parse_routes(out) == {"O*IA": 1, "O IA": 1, "O E2": 1}


def test_ifname():
    assert ifname("e1/0") == "Ethernet1/0" and ifname("Fa0/0") == "FastEthernet0/0" and ifname("lo1") == "Loopback1"


def test_ios_mode_fallback():
    # `no ip route` typed inside router ospf mode is a global command: IOS leaves the sub-mode for it
    cfg = parse_config("ip route 172.16.99.0 255.255.255.0 Null0\nrouter ospf 1\n redistribute static subnets\n"
                       "no ip route 172.16.99.0 255.255.255.0 Null0\n area 1 stub\n", "R1")
    assert cfg.statics == []
    assert "static" in cfg.ospf.redistribute and cfg.ospf.areas == {}
