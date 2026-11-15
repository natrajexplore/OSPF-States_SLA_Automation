"""Everyday IOS commands on the simulated routers (app/sim/iosshow.py and the SSH shell's command parser)."""
import pytest

from app.sim.driver import lab
from app.sim.render import INVALID
from app.sim.sshd import ParseError, help_for, parse


@pytest.fixture(autouse=True)
def fresh():
    lab().reset_all()


@pytest.mark.parametrize("cmd, expect", [
    ("show running-config", "hostname R3"),
    ("show startup-config", "Using "),
    ("show interfaces Ethernet1/0", "Internet address is 10.0.123.3/24"),
    ("show interfaces description", "=== area 0 LAN"),
    ("show ip interface brief", "Ethernet1/7"),
    ("show ip interface Ethernet1/0", "Internet address is 10.0.123.3/24"),
    ("show ip protocols", 'Routing Protocol is "ospf 1"'),
    ("show ip route summary", "ospf 1"),
    ("show cdp neighbors", "R4.lab.local"),
    ("show ip arp", "10.1.34.2"),
    ("show ip vrf", "MGMT"),
    ("show ip cef", "attached"),
    ("show logging", "%SYS-5-RESTART"),
    ("show version", "Configuration register is 0x2102"),
    ("show inventory", "PA-8E"),
    ("show processes cpu", "CPU utilization"),
    ("show ip ospf neighbor Ethernet1/1", "10.255.0.4"),
    ("show ip ospf database database-summary", "Area 0 database summary"),
    ("show ip route vrf MGMT", "192.168.99.1"),
])
def test_show_commands(cmd, expect):
    out = lab().show("R3", cmd)
    assert out != INVALID and expect in out, out[:300]


def test_running_config_hides_passwords_and_follows_changes():
    run = lab().show("R4", "show running-config")
    assert "secret 5 $1$" in run and "lab123" not in run
    lab().push("R4", ["interface Ethernet1/0", " ip ospf cost 77"], save=False)
    assert " ip ospf cost 77" in lab().show("R4", "show running-config")
    assert " ip ospf cost 77" not in lab().show("R4", "show startup-config")       # not saved yet
    lab().write_mem("R4")
    assert " ip ospf cost 77" in lab().show("R4", "show startup-config")


def test_abbreviations_and_pipes():
    assert "Ethernet1/0" in lab().show("R3", "sh ip int br | inc Ethernet1/0")
    assert "Loopback0" not in lab().show("R3", "sh ip int br | exclude Loopback")
    sec = lab().show("R3", "sh run | sec router ospf")
    assert sec.startswith("router ospf 1") and "router-id 10.255.0.3" in sec


def test_parser_like_ios():
    assert parse("sh ip pro") == ["show", "ip", "protocols"]
    assert parse("sh ip int br") == ["show", "ip", "interface", "brief"]
    assert parse("conf t") == ["configure", "terminal"]
    assert parse("sh int e1/0") == ["show", "interfaces", "e1/0"]
    for bad, kind in (("sh i", "ambiguous"), ("sh ip", "incomplete"), ("show asdf", "invalid")):
        with pytest.raises(ParseError) as e:
            parse(bad)
        assert e.value.kind == kind
    assert "protocols" in help_for("show ip ")
    assert help_for("sh ip o") == ["ospf"]


def test_adjacency_changes_are_logged():
    lab().push("R4", ["interface Ethernet1/0", " ip ospf hello-interval 5"], save=False)
    lab().show("R3", "show ip ospf neighbor")
    log = lab().show("R3", "show logging")
    assert "%OSPF-5-ADJCHG: Process 1, Nbr 10.255.0.4 on Ethernet1/1 from FULL to DOWN" in log
    assert "%SYS-5-CONFIG_I: Configured from console by lab" in lab().show("R4", "show logging")


def test_ping_and_traceroute():
    from app.sim.iosshow import ping, traceroute
    snap = lab().snapshot()
    assert "!!!!!" in ping(lab().model, snap, "R4", "10.255.0.1")
    assert "....." in ping(lab().model, snap, "R4", "10.99.99.99")
    tr = traceroute(lab().model, snap, "R4", "10.255.0.1")
    assert "1 10.1.3" in tr or "1 10.1.2" in tr
    assert "10.255.0.1" in tr.splitlines()[-1]


def test_tab_completion_like_ios():
    from app.sim.clitree import complete, config_tree
    from app.sim.sshd import TREE
    assert complete("sh", TREE) == "show "
    assert complete("sh ip ospf ne", TREE) == "sh ip ospf neighbor "
    assert complete("sh ip int br", TREE) == "sh ip int brief "
    assert complete("sh int e", TREE) == "sh int Ethernet"                 # interface type, no space: type 1/0
    assert complete("sh i", TREE) is None                                  # interfaces / ip / inventory: ambiguous
    assert complete("show ip ", TREE) is None
    cfg = config_tree(("global",), TREE)
    assert complete("int f", cfg) == "int FastEthernet"
    assert complete("router o", cfg) == "router ospf "
    ifc = config_tree(("if", "Ethernet1/0"), TREE)
    assert complete("ip ospf hel", ifc) == "ip ospf hello-interval "
    assert complete("no shut", ifc) == "no shutdown "
    assert complete("do sh ip ro", ifc) == "do sh ip route "
    rtr = config_tree(("ospf",), TREE)
    assert complete("area 1 nssa no-s", rtr) == "area 1 nssa no-summary "


def test_question_mark_help_like_ios():
    from app.sim.clitree import config_tree, describe, help_for
    from app.sim.sshd import TREE
    assert help_for("sh ip o", TREE) == ["ospf"]
    words = help_for("show ip ospf ", TREE)
    assert "neighbor" in words and "<cr>" in words
    assert "Neighbor list" in describe(words)
    assert help_for("show interfaces ", TREE)[:1] == ["description"] and "Ethernet" in help_for("show interfaces ", TREE)
    ifc = config_tree(("if", "Ethernet1/0"), TREE)
    assert {"hello-interval", "cost", "network"} <= set(help_for("ip ospf ", ifc))


def test_negated_commands_need_no_arguments():
    from app.sim.clitree import config_tree, parse
    from app.sim.sshd import TREE
    ifc = config_tree(("if", "Ethernet1/0"), TREE)
    assert parse("no ip add", ifc) == ["no", "ip", "address"]
    assert parse("no ip ospf cost", ifc) == ["no", "ip", "ospf", "cost"]
    assert "<cr>" not in __import__("app.sim.clitree", fromlist=["help_for"]).help_for("ip address ", ifc)
