"""A small Cisco IOS configuration model: parse configuration lines (a baseline file or a pushed config set) into the
state the OSPF model needs, the same way IOS does it: a line that is not a sub-command of the current mode drops back
to global configuration mode."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

_IF_FAMILIES = ("FastEthernet", "GigabitEthernet", "Ethernet", "Loopback", "Serial", "Tunnel", "Vlan", "Null")


def ifname(raw: str) -> str:
    """e1/0, Et1/0, eth1/0 -> Ethernet1/0; fa0/0 -> FastEthernet0/0; lo1 -> Loopback1."""
    m = re.fullmatch(r"\s*([A-Za-z-]+)\s*(\d[\d/.:]*)\s*", raw)
    if not m:
        return raw.strip()
    prefix, num = m.group(1).lower(), m.group(2)
    for fam in _IF_FAMILIES:
        if fam.lower().startswith(prefix):
            return fam + num
    return m.group(1) + num


def short_if(name: str) -> str:
    """Ethernet1/0 -> Et1/0, FastEthernet0/0 -> Fa0/0, Loopback0 -> Lo0 (as `show ... brief` prints them)."""
    for fam, abbr in (("FastEthernet", "Fa"), ("GigabitEthernet", "Gi"), ("Ethernet", "Et"), ("Loopback", "Lo"),
                      ("Serial", "Se"), ("Tunnel", "Tu")):
        if name.startswith(fam):
            return abbr + name[len(fam):]
    return name


def parse_area(raw: str) -> int:
    if "." in raw:
        a, b, c, d = (int(x) for x in raw.split("."))
        return (a << 24) | (b << 16) | (c << 8) | d
    return int(raw)


@dataclass
class Iface:
    name: str
    description: str = ""
    vrf: str | None = None
    ip: str | None = None
    mask: str | None = None
    shutdown: bool = False
    # OSPFv2
    ospf_area: int | None = None
    net_type: str | None = None              # point-to-point / broadcast / None = the interface's default
    priority: int = 1
    hello: int | None = None
    dead: int | None = None
    dead_minimal_mult: int | None = None     # `ip ospf dead-interval minimal hello-multiplier N`
    cost: int | None = None
    mtu: int = 1500
    ospf_bfd: bool = False
    bfd: tuple[int, int, int] | None = None   # interval, min_rx, multiplier
    # OSPFv3
    v6_addrs: list[str] = field(default_factory=list)
    v6_area: int | None = None
    v6_instance: int = 0
    v6_net_type: str | None = None
    v6_priority: int = 1

    @property
    def loopback(self) -> bool:
        return self.name.startswith("Loopback")


@dataclass
class Area:
    kind: str = "normal"                     # normal / stub / nssa
    no_summary: bool = False
    translate_always: bool = False


@dataclass
class OspfProc:
    pid: int = 1
    router_id: str | None = None
    areas: dict[int, Area] = field(default_factory=dict)
    redistribute: dict[str, dict] = field(default_factory=dict)   # static/connected -> {subnets, metric, mtype, route_map}
    ref_bw: int = 100
    log_adj: str | None = None

    def area(self, a: int) -> Area:
        return self.areas.get(a) or Area()


@dataclass
class RouterConfig:
    hostname: str
    ifaces: dict[str, Iface] = field(default_factory=dict)
    ospf: OspfProc | None = None
    ospf6: OspfProc | None = None
    v6_routing: bool = False
    statics: list[tuple[str, str, str, str | None]] = field(default_factory=list)   # prefix, mask, next hop, vrf
    route_maps: dict[str, list[dict]] = field(default_factory=dict)                  # name -> [{seq, action, match_ifaces}]
    sla: dict[int, dict] = field(default_factory=dict)
    sla_scheduled: set[int] = field(default_factory=set)

    def iface(self, name: str) -> Iface:
        name = ifname(name)
        if name not in self.ifaces:
            self.ifaces[name] = Iface(name)
        return self.ifaces[name]

    def clone(self) -> "RouterConfig":
        return copy.deepcopy(self)


# Lines that are global configuration commands in any mode (IOS leaves the sub-mode for them).
_GLOBAL = re.compile(
    r"^(no )?(hostname |interface |router |ipv6 router |ipv6 unicast-routing|ip route |ipv6 route |route-map |"
    r"ip sla |ip vrf (?!forwarding)|vrf definition |line |enable |username |ip domain|ip cef|ipv6 cef|end$|exit$|"
    r"service |logging |banner |crypto |ip ssh |ntp |snmp-server |access-list |ip access-list |ip prefix-list |"
    r"key chain |boot|version |control-plane|mpls |bfd-template |track |event manager )"
)
_IF_SUB = re.compile(r"^(no )?(ip |ipv6 |description|shutdown|bfd |duplex|speed|mtu |load-interval|media-type|negotiation|"
                     r"cdp |keepalive|bandwidth |delay |standby |vrrp |encapsulation )")
_OSPF_SUB = re.compile(r"^(no )?(router-id|log-adjacency-changes|area |redistribute |auto-cost|network |passive-interface|"
                       r"default-information|distance|timers |max-metric|summary-address|default-metric|bfd |nsf|"
                       r"address-family|exit-address-family)")
_RMAP_SUB = re.compile(r"^(no )?(match |set |description|continue)")
_SLA_SUB = re.compile(r"^(no )?(icmp-echo |frequency |timeout |threshold |tag |tos |request-data-size |vrf |owner |history )")


class ConfigSession:
    """Applies configuration lines to a RouterConfig and records the IOS prompts they were typed at."""

    def __init__(self, cfg: RouterConfig) -> None:
        self.cfg = cfg
        self.mode: tuple = ("global",)
        self.transcript: list[str] = []
        self.errors: list[str] = []

    @property
    def prompt(self) -> str:
        kind = self.mode[0]
        sub = {"global": "config", "if": "config-if", "ospf": "config-router", "ospf6": "config-rtr",
               "rmap": "config-route-map", "sla": "config-ip-sla-echo", "other": "config-line"}[kind]
        return f"{self.cfg.hostname}({sub})#"

    def apply(self, lines: list[str]) -> None:
        for raw in lines:
            s = " ".join(raw.split())
            if not s or s.startswith("!"):
                continue
            self.transcript.append(self.prompt + raw.rstrip())
            if self.mode[0] == "if" and _IF_SUB.match(s) and not _GLOBAL.match(s):
                self._iface(self.cfg.iface(self.mode[1]), s)
            elif self.mode[0] in ("ospf", "ospf6") and _OSPF_SUB.match(s):
                self._ospf(self.cfg.ospf if self.mode[0] == "ospf" else self.cfg.ospf6, s)
            elif self.mode[0] == "rmap" and _RMAP_SUB.match(s):
                self._rmap(s)
            elif self.mode[0] == "sla" and _SLA_SUB.match(s):
                self._sla(s)
            elif self.mode[0] == "other" and not _GLOBAL.match(s):
                pass                                              # line vty / ip vrf sub-commands: not modelled
            else:
                self._global(s)

    # -- global ------------------------------------------------------------------------------------------------
    def _global(self, s: str) -> None:
        cfg = self.cfg
        neg = s.startswith("no ")
        body = s[3:] if neg else s
        self.mode = ("global",)
        if m := re.fullmatch(r"hostname (\S+)", body):
            if not neg:
                cfg.hostname = m.group(1)
        elif m := re.fullmatch(r"interface (\S+(?: \S+)?)", body):
            name = ifname(m.group(1))
            if neg:
                cfg.ifaces.pop(name, None)
            else:
                cfg.iface(name)
                self.mode = ("if", name)
        elif m := re.fullmatch(r"router ospf (\d+)(?: vrf \S+)?", body):
            if neg:
                cfg.ospf = None
            else:
                cfg.ospf = cfg.ospf or OspfProc(pid=int(m.group(1)))
                self.mode = ("ospf",)
        elif m := re.fullmatch(r"ipv6 router ospf (\d+)", body):
            if neg:
                cfg.ospf6 = None
                for i in cfg.ifaces.values():                 # IOS removes the interface commands with the process
                    i.v6_area, i.v6_instance = None, 0
            else:
                cfg.ospf6 = cfg.ospf6 or OspfProc(pid=int(m.group(1)))
                self.mode = ("ospf6",)
        elif body == "ipv6 unicast-routing":
            cfg.v6_routing = not neg
        elif m := re.fullmatch(r"ip route (?:vrf (\S+) )?(\S+) (\S+) (\S+)(?: \d+)?(?: .*)?", body):
            vrf, prefix, mask, nh = m.group(1), m.group(2), m.group(3), m.group(4)
            cfg.statics = [r for r in cfg.statics if not (r[0] == prefix and r[1] == mask and r[3] == vrf)]
            if not neg:
                cfg.statics.append((prefix, mask, nh, vrf))
        elif m := re.fullmatch(r"route-map (\S+)(?: (permit|deny))?(?: (\d+))?", body):
            name = m.group(1)
            if neg:
                cfg.route_maps.pop(name, None)
            else:
                seq = int(m.group(3) or 10)
                entries = cfg.route_maps.setdefault(name, [])
                if not any(e["seq"] == seq for e in entries):
                    entries.append({"seq": seq, "action": m.group(2) or "permit", "match_ifaces": []})
                self.mode = ("rmap", name, seq)
        elif m := re.fullmatch(r"ip sla schedule (\d+).*", body):
            (cfg.sla_scheduled.discard if neg else cfg.sla_scheduled.add)(int(m.group(1)))
        elif m := re.fullmatch(r"ip sla (\d+)", body):
            sid = int(m.group(1))
            if neg:
                cfg.sla.pop(sid, None)
                cfg.sla_scheduled.discard(sid)
            else:
                cfg.sla.setdefault(sid, {"type": None, "target": None, "source": None, "frequency": 60})
                self.mode = ("sla", sid)
        elif re.match(r"(ip vrf |vrf definition |line |key chain |control-plane)", body):
            self.mode = ("other",)

    # -- interface ---------------------------------------------------------------------------------------------
    def _iface(self, i: Iface, s: str) -> None:
        neg = s.startswith("no ")
        body = s[3:] if neg else s
        if m := re.fullmatch(r"description (.*)", body):
            i.description = "" if neg else m.group(1)
        elif m := re.fullmatch(r"ip vrf forwarding (\S+)", body):
            i.vrf = None if neg else m.group(1)
        elif m := re.fullmatch(r"ip address(?: (\S+) (\S+))?(?: secondary)?", body):
            if neg:
                i.ip = i.mask = None
            elif m.group(1):
                i.ip, i.mask = m.group(1), m.group(2)
        elif body == "shutdown":
            i.shutdown = not neg
        elif m := re.fullmatch(r"ip ospf \d+ area(?: (\S+))?", body):
            i.ospf_area = None if neg else parse_area(m.group(1))
        elif m := re.fullmatch(r"ip ospf network(?: (\S+))?(?: .*)?", body):
            i.net_type = None if neg else m.group(1)
        elif m := re.fullmatch(r"ip ospf priority(?: (\d+))?", body):
            i.priority = 1 if neg else int(m.group(1))
        elif m := re.fullmatch(r"ip ospf hello-interval(?: (\d+))?", body):
            i.hello = None if neg else int(m.group(1))
        elif re.fullmatch(r"ip ospf dead-interval minimal hello-multiplier(?: \d+)?", body) and neg:
            i.dead_minimal_mult = None
        elif m := re.fullmatch(r"ip ospf dead-interval minimal hello-multiplier (\d+)", body):
            i.dead_minimal_mult, i.dead = int(m.group(1)), None
        elif m := re.fullmatch(r"ip ospf dead-interval(?: (\d+))?", body):
            i.dead = None if neg else int(m.group(1))
            if not neg:
                i.dead_minimal_mult = None
        elif m := re.fullmatch(r"ip ospf cost(?: (\d+))?", body):
            i.cost = None if neg else int(m.group(1))
        elif m := re.fullmatch(r"ip mtu(?: (\d+))?", body):
            i.mtu = 1500 if neg else int(m.group(1))
        elif body == "ip ospf bfd" or body.startswith("ip ospf bfd "):
            i.ospf_bfd = not neg
        elif m := re.fullmatch(r"bfd interval(?: (\d+) min_rx (\d+) multiplier (\d+))?", body):
            i.bfd = None if neg else (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m := re.fullmatch(r"ipv6 address(?: (\S+))?(?: .*)?", body):
            if neg:
                i.v6_addrs = [a for a in i.v6_addrs if m.group(1) and a.lower() != m.group(1).lower()]
            elif m.group(1) and m.group(1).lower() not in (a.lower() for a in i.v6_addrs):
                i.v6_addrs.append(m.group(1))
        elif m := re.fullmatch(r"ipv6 ospf \d+ area (\S+)(?: instance (\d+))?", body):
            inst = int(m.group(2) or 0)
            if neg:
                if i.v6_area == parse_area(m.group(1)) and i.v6_instance == inst:
                    i.v6_area, i.v6_instance = None, 0
            else:
                i.v6_area, i.v6_instance = parse_area(m.group(1)), inst
        elif m := re.fullmatch(r"ipv6 ospf network(?: (\S+))?", body):
            i.v6_net_type = None if neg else m.group(1)
        elif m := re.fullmatch(r"ipv6 ospf priority(?: (\d+))?", body):
            i.v6_priority = 1 if neg else int(m.group(1))

    # -- router ospf / ipv6 router ospf ----------------------------------------------------------------------
    def _ospf(self, p: OspfProc, s: str) -> None:
        neg = s.startswith("no ")
        body = s[3:] if neg else s
        if m := re.fullmatch(r"router-id(?: (\S+))?", body):
            p.router_id = None if neg else m.group(1)
        elif m := re.fullmatch(r"log-adjacency-changes(?: (detail))?", body):
            p.log_adj = None if neg else (m.group(1) or "")
        elif m := re.fullmatch(r"auto-cost reference-bandwidth(?: (\d+))?", body):
            p.ref_bw = 100 if neg else int(m.group(1))
        elif m := re.fullmatch(r"area (\S+) (stub|nssa)( no-summary)?", body):
            a = parse_area(m.group(1))
            cur = p.areas.get(a) or Area()
            if neg:
                if m.group(3) and cur.kind == m.group(2):
                    cur.no_summary = False                    # `no area 1 stub no-summary` keeps the stub area
                elif cur.kind == m.group(2):
                    cur = Area()
            else:
                cur.kind, cur.no_summary = m.group(2), bool(m.group(3))
            p.areas[a] = cur
        elif m := re.fullmatch(r"area (\S+) nssa translate type7 always", body):
            a = parse_area(m.group(1))
            cur = p.areas.get(a) or Area()
            if neg:
                cur.translate_always = False
            else:
                cur.kind, cur.translate_always = "nssa", True
            p.areas[a] = cur
        elif m := re.fullmatch(r"redistribute (static|connected)(.*)", body):
            if neg:
                p.redistribute.pop(m.group(1), None)
            else:
                opts = m.group(2)
                metric = re.search(r"metric (\d+)", opts)
                mtype = re.search(r"metric-type (\d)", opts)
                rmap = re.search(r"route-map (\S+)", opts)
                p.redistribute[m.group(1)] = {
                    "subnets": " subnets" in f" {opts}", "metric": int(metric.group(1)) if metric else 20,
                    "mtype": int(mtype.group(1)) if mtype else 2, "route_map": rmap.group(1) if rmap else None,
                }

    def _rmap(self, s: str) -> None:
        entry = next(e for e in self.cfg.route_maps[self.mode[1]] if e["seq"] == self.mode[2])
        neg = s.startswith("no ")
        body = s[3:] if neg else s
        if m := re.fullmatch(r"match interface (.+)", body):
            names = [ifname(x) for x in m.group(1).split()]
            entry["match_ifaces"] = [] if neg else names

    def _sla(self, s: str) -> None:
        op = self.cfg.sla[self.mode[1]]
        if m := re.fullmatch(r"icmp-echo (\S+)(?: source-interface (\S+))?.*", s):
            op.update(type="icmp-echo", target=m.group(1), source=ifname(m.group(2)) if m.group(2) else None)
        elif m := re.fullmatch(r"frequency (\d+)", s):
            op["frequency"] = int(m.group(1))


def parse_config(text: str, hostname: str) -> RouterConfig:
    cfg = RouterConfig(hostname=hostname)
    ConfigSession(cfg).apply(text.splitlines())
    return cfg


def render_ospf_section(cfg: RouterConfig, v6: bool = False) -> str:
    """`show running-config | section router ospf` (also matches `ipv6 router ospf`, as on IOS)."""
    out = []
    for proc, header in ((cfg.ospf, "router ospf"), (cfg.ospf6, "ipv6 router ospf")):
        if proc is None or (v6 and header == "router ospf"):
            continue
        out.append(f"{header} {proc.pid}")
        if proc.router_id:
            out.append(f" router-id {proc.router_id}")
        if proc.ref_bw != 100:
            out.append(f" auto-cost reference-bandwidth {proc.ref_bw}")
        if proc.log_adj is not None:
            out.append(f" log-adjacency-changes{' ' + proc.log_adj if proc.log_adj else ''}")
        for a, ar in sorted(proc.areas.items()):
            if ar.kind == "stub":
                out.append(f" area {a} stub{' no-summary' if ar.no_summary else ''}")
            elif ar.kind == "nssa":
                out.append(f" area {a} nssa{' no-summary' if ar.no_summary else ''}")
                if ar.translate_always:
                    out.append(f" area {a} nssa translate type7 always")
        for src, r in proc.redistribute.items():
            line = f" redistribute {src}"
            if r["metric"] != 20 or src == "static":
                line += f" metric {r['metric']}"
            if r["mtype"] != 2:
                line += f" metric-type {r['mtype']}"
            if r["subnets"]:
                line += " subnets"
            if r["route_map"]:
                line += f" route-map {r['route_map']}"
            out.append(line)
    return "\n".join(out)
