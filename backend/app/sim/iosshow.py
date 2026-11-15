"""The everyday IOS commands of a simulated router, beyond the OSPF views in render.py: show running-config /
startup-config, show interfaces, show ip interface, show ip protocols, show ip route summary, ARP, CDP, CEF, VRF,
logging, version, inventory, processes, memory, flash, lines, and ping / traceroute over the simulated routing tables.

Everything is derived from the router's current configuration (iosconfig.RouterConfig) and the OSPF model's snapshot,
so it stays consistent with show ip ospf / show ip route and changes when a scenario or a PuTTY user changes the router.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import time

from .iosconfig import Iface, RouterConfig, ifname, render_ospf_section, short_if

# a c7200 with an NPE-400, the C7200-IO-FE (FastEthernet0/0) and a PA-8E in slot 1 (Ethernet1/0 - 1/7), as in EVE-NG
HARDWARE = ["FastEthernet0/0"] + [f"Ethernet1/{p}" for p in range(8)]
IMAGE = "c7200-adventerprisek9-mz.152-4.S6"


def if_sort_key(name: str):
    nums = [int(x) for x in re.findall(r"\d+", name)]
    return (0 if name.startswith("Loopback") else 1, nums)


def _secret_hash(text: str) -> str:
    """A stable stand-in for IOS's type-5 hash, so the running-config never shows a password in clear."""
    h = hashlib.sha256(text.encode()).hexdigest()
    alphabet = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    salt = "".join(alphabet[int(h[k:k + 2], 16) % 64] for k in range(0, 8, 2))
    body = "".join(alphabet[int(h[k:k + 2], 16) % 64] for k in range(8, 52, 2))
    return f"$1${salt}${body}"


def _hide(line: str) -> str:
    """enable secret lab123 -> enable secret 5 $1$...; username x privilege 15 secret y -> ... secret 5 $1$..."""
    m = re.fullmatch(r"(enable secret|username \S+(?: privilege \d+)? secret) (?:0 )?(\S+)", line)
    if m and not line.split()[-2] == "5":
        return f"{m.group(1)} 5 {_secret_hash(m.group(1) + m.group(2))}"     # salted per user, like IOS
    return line


def _mask_bits(mask: str | None) -> int:
    try:
        return ipaddress.ip_network(f"0.0.0.0/{mask}").prefixlen if mask else 0
    except ValueError:
        return 0


def render_running_config(cfg: RouterConfig, changed: float | None = None, user: str = "lab") -> str:
    """The whole configuration as `show running-config` prints it."""
    out = ["!"]
    if changed:
        out.append(f"! Last configuration change at {time.strftime('%H:%M:%S UTC %a %b %d %Y', time.gmtime(changed))} by {user}")
        out.append("!")
    out += ["version 15.2", "service timestamps debug datetime msec", "service timestamps log datetime msec",
            "no service password-encryption", "!", f"hostname {cfg.hostname}", "!", "boot-start-marker",
            "boot-end-marker", "!", "!"]
    misc = [_hide(x) for x in cfg.misc]
    first = [x for x in misc if x.startswith(("enable ", "aaa "))]
    out += first + (["!"] if first else [])
    for head, subs in cfg.blocks.items():
        if head.startswith(("ip vrf", "vrf definition")):
            out += [head] + [f" {x}" for x in subs] + ["!"]
    domain = [x for x in misc if re.match(r"(no )?ip (domain|cef|name-server)", x)]
    out += domain + ["ip cef"] + (["ipv6 unicast-routing", "ipv6 cef"] if cfg.v6_routing else ["no ipv6 cef"]) + ["!"]
    users = [x for x in misc if x.startswith("username ")]
    out += ["multilink bundle-name authenticated", "!"] + users + (["!"] if users else [])
    rest = [x for x in misc if x not in first and x not in domain and x not in users]
    out += rest + (["!"] if rest else [])
    out += ["ip tcp synwait-time 5", "!"]
    for i in sorted(cfg.ifaces.values(), key=lambda i: if_sort_key(i.name)):
        out.append(f"interface {i.name}")
        if i.description:
            out.append(f" description {i.description}")
        if i.vrf:
            out.append(f" ip vrf forwarding {i.vrf}")
        out.append(f" ip address {i.ip} {i.mask}" if i.ip else " no ip address")
        if i.mtu != 1500:
            out.append(f" ip mtu {i.mtu}")
        if i.hello:
            out.append(f" ip ospf hello-interval {i.hello}")
        if i.dead_minimal_mult:
            out.append(f" ip ospf dead-interval minimal hello-multiplier {i.dead_minimal_mult}")
        elif i.dead:
            out.append(f" ip ospf dead-interval {i.dead}")
        if i.net_type:
            out.append(f" ip ospf network {i.net_type}")
        if i.priority != 1:
            out.append(f" ip ospf priority {i.priority}")
        if i.cost is not None:
            out.append(f" ip ospf cost {i.cost}")
        if i.ospf_bfd:
            out.append(" ip ospf bfd")
        if i.ospf_area is not None:
            out.append(f" ip ospf {cfg.ospf.pid if cfg.ospf else 1} area {i.ospf_area}")
        if i.bfd:
            out.append(f" bfd interval {i.bfd[0]} min_rx {i.bfd[1]} multiplier {i.bfd[2]}")
        out += [f" ipv6 address {a}" for a in i.v6_addrs]
        if i.v6_net_type:
            out.append(f" ipv6 ospf network {i.v6_net_type}")
        if i.v6_priority != 1:
            out.append(f" ipv6 ospf priority {i.v6_priority}")
        if i.v6_area is not None:
            out.append(f" ipv6 ospf {cfg.ospf6.pid if cfg.ospf6 else 1} area {i.v6_area}"
                       + (f" instance {i.v6_instance}" if i.v6_instance else ""))
        out += [f" {x}" for x in i.extra]
        if i.shutdown:
            out.append(" shutdown")
        out.append("!")
    if cfg.ospf:
        sec = render_ospf_section(RouterConfig(cfg.hostname, ospf=cfg.ospf)).splitlines()
        out += sec + [f" {x}" for x in cfg.ospf.extra] + ["!"]
    if cfg.ospf6:
        sec = render_ospf_section(RouterConfig(cfg.hostname, ospf6=cfg.ospf6), v6=True).splitlines()
        out += sec + [f" {x}" for x in cfg.ospf6.extra] + ["!"]
    out += ["ip forward-protocol nd", "!", "!", "no ip http server", "no ip http secure-server"]
    for prefix, mask, nh, vrf in cfg.statics:
        out.append(f"ip route {'vrf ' + vrf + ' ' if vrf else ''}{prefix} {mask} {nh}")
    out.append("!")
    for sid, op in sorted(cfg.sla.items()):
        out.append(f"ip sla {sid}")
        if op.get("line"):
            out.append(f" {op['line']}")
        if op.get("frequency", 60) != 60:
            out.append(f" frequency {op['frequency']}")
        if sid in cfg.sla_schedule_line:
            out.append(cfg.sla_schedule_line[sid])
    for name, entries in cfg.route_maps.items():
        for e in sorted(entries, key=lambda e: e["seq"]):
            out.append(f"route-map {name} {e['action']} {e['seq']}")
            if e["match_ifaces"]:
                out.append(f" match interface {' '.join(e['match_ifaces'])}")
            out.append("!")
    out += ["!", "!", "control-plane", "!", "!", "line con 0", " exec-timeout 0 0", " privilege level 15",
            " logging synchronous", " stopbits 1", "line aux 0", " exec-timeout 0 0", " privilege level 15",
            " logging synchronous", " stopbits 1"]
    for head, subs in cfg.blocks.items():
        if head.startswith("line ") and head not in ("line con 0", "line aux 0"):
            out += [head] + [f" {x}" for x in subs]
    out += ["!", "!", "end"]
    body = "\n".join(out) + "\n"
    return f"Building configuration...\n\nCurrent configuration : {len(body)} bytes\n{body}"


def section(text: str, pattern: str) -> str:
    """`| section <regex>`: every top-level block whose header matches, with its indented lines."""
    try:
        rx = re.compile(pattern)
    except re.error:
        return "% Invalid regular expression\n"
    out, keep = [], False
    for ln in text.splitlines():
        if ln and not ln.startswith(" "):
            keep = bool(rx.search(ln))
        elif ln.startswith(" ") and rx.search(ln) and not keep:
            out.append(ln)
            continue
        if keep and ln:
            out.append(ln)
    return "\n".join(out) + ("\n" if out else "")


class IosShow:
    """The commands render.Renderer does not answer. `show()` returns None when it does not know the command either."""

    def __init__(self, renderer) -> None:
        self.R = renderer
        self.m, self.s, self.now = renderer.m, renderer.s, renderer.now
        self.lab = getattr(renderer, "lab", None)

    # -- helpers --------------------------------------------------------------------------------------------------
    def cfg(self, r: str) -> RouterConfig:
        return self.m.configs[r]

    def idx(self, r: str) -> int:
        return sorted(self.m.configs).index(r) + 1

    def mac(self, r: str, name: str) -> str:
        nums = [int(x) for x in re.findall(r"\d+", name)] + [0, 0]
        return f"ca{self.idx(r):02x}.{(0x0b1c + 0x111 * self.idx(r)) & 0xffff:04x}.{nums[0]:02x}{nums[1] * 4 + 0x1c:02x}"

    def find_if(self, r: str, raw: str) -> Iface | None:
        name = ifname(raw)
        return self.cfg(r).ifaces.get(name) or next(
            (i for n, i in self.cfg(r).ifaces.items() if n.lower() == name.lower()), None)

    def line_up(self, r: str, i: Iface) -> bool:
        return not i.shutdown

    def uptime(self) -> float:
        return self.now - (self.lab.started if self.lab else self.R.started)

    def bw(self, name: str) -> int:
        return 8000000 if name.startswith("Loopback") else 100000 if name.startswith("FastEthernet") else 10000

    def peers(self, r: str):
        """(local iface, peer router, peer iface) for every inventory link of r."""
        for ln in self.m.links:
            mine = [ifn for node, ifn in ln["members"] if node == r]
            for ifn in mine:
                for node, pif in ln["members"]:
                    if node != r:
                        yield ifn, node, pif

    # -- dispatch ---------------------------------------------------------------------------------------------------
    def show(self, r: str, c: str) -> str | None:
        table = [
            (r"show (?:running-config|run)", lambda m: self.running(r)),
            (r"show (?:running-config|run) interface (\S+)", lambda m: self.running_if(r, m.group(1))),
            (r"show (?:running-config|run) \| (?:section|sec) (.+)", lambda m: section(self.running(r), m.group(1))),
            (r"show startup-config", lambda m: self.startup(r)),
            (r"show interfaces? description", lambda m: self.if_description(r)),
            (r"show interfaces?(?: (\S+))?", lambda m: self.interfaces(r, m.group(1))),
            (r"show interfaces? (\S+) brief", lambda m: self.R.v4_if_brief(r)),
            (r"show ip interface(?: (\S+))?", lambda m: self.ip_interface(r, m.group(1))),
            (r"show ip protocols(?: summary)?", lambda m: self.protocols(r)),
            (r"show ip route summary", lambda m: self.route_summary(r)),
            (r"show ip route (connected|static|local)", lambda m: self.route_filtered(r, m.group(1))),
            (r"show ip route vrf (\S+)", lambda m: self.route_vrf(r, m.group(1))),
            (r"show ip (?:arp|neighbors)(?: vrf (\S+))?", lambda m: self.arp(r, m.group(1))),
            (r"show arp", lambda m: self.arp(r, None, all_vrfs=True)),
            (r"show cdp neighbors?( detail)?", lambda m: self.cdp(r, bool(m.group(1)))),
            (r"show cdp", lambda m: "Global CDP information:\n\tSending CDP packets every 60 seconds\n\tSending a holdtime value of 180 seconds\n\tSending CDPv2 advertisements is  enabled\n"),
            (r"show ip vrf(?: (?:brief|detail))?", lambda m: self.vrfs(r)),
            (r"show ip cef(?: (\S+))?", lambda m: self.cef(r, m.group(1))),
            (r"show logging", lambda m: self.logging(r)),
            (r"show inventory", lambda m: self.inventory(r)),
            (r"show (?:processes cpu|proc cpu)(?: sorted)?(?: 5sec| 1min| 5min)?", lambda m: self.cpu()),
            (r"show (?:processes cpu history)", lambda m: self.cpu()),
            (r"show memory(?: statistics| summary)?", lambda m: self.memory()),
            (r"show (?:flash:?|disk0:?|bootflash:?)(?: all)?", lambda m: self.flash()),
            (r"dir(?: (?:flash|disk0|nvram):?)?", lambda m: self.flash()),
            (r"show line(?: summary)?", lambda m: self.lines(r)),
            (r"show ntp (?:status|associations)", lambda m: "%NTP is not enabled.\n"),
            (r"show snmp(?: .*)?", lambda m: "%SNMP agent not enabled\n"),
            (r"show (?:access-lists|ip access-lists)(?: \S+)?", lambda m: ""),
            (r"show (?:standby|vrrp|track|ip nat translations)(?: brief)?", lambda m: ""),
            (r"show route-map(?: (\S+))?", lambda m: self.route_map(r, m.group(1))),
            (r"show ip ospf neighbor (\S+)", lambda m: self.ospf_nbr_if(r, m.group(1))),
            (r"show ip ospf statistics(?: detail)?", lambda m: self.ospf_stats(r)),
            (r"show ip ospf traffic(?: \S+)?", lambda m: self.ospf_traffic(r)),
            (r"show ip ospf events", lambda m: self.ospf_events(r)),
            (r"show ip ospf rib", lambda m: self.ospf_rib(r)),
            (r"show ip ospf (?:virtual-links|sham-links|summary-address|request-list|retransmission-list|flood-list)",
             lambda m: ""),
            (r"show ip ospf database database-summary", lambda m: self.ospf_db_summary(r)),
            (r"show ip sla (?:summary|statistics aggregated)", lambda m: self.sla_summary(r)),
            (r"show ip sla configuration(?: \d+)?", lambda m: self.sla_config(r)),
            (r"show privilege", lambda m: "Current privilege level is 15\n"),
            (r"show users", lambda m: None),
            (r"show (?:history|terminal)", lambda m: None),
            (r"show (?:ipv6 )?protocols", lambda m: self.protocols(r)),
            (r"show (?:hosts|ip hosts)", lambda m: self.hosts(r)),
            (r"show boot|show bootvar", lambda m: f"BOOT variable = disk0:{IMAGE},1;\nCONFIG_FILE variable = \nBOOTLDR variable does not exist\nConfiguration register is 0x2102\n"),
            (r"show environment(?: all)?", lambda m: "Power Supplies:\n  Power Supply 1 is AC power supply. Unit is on.\nAll measured values are normal\n"),
            (r"show (?:diag|controllers)(?: \S+)?", lambda m: self.inventory(r)),
            (r"show (?:debugging|debug)", lambda m: ""),
            (r"show tech-support", lambda m: self.tech(r)),
        ]
        for pat, fn in table:
            mt = re.fullmatch(pat, c, re.IGNORECASE)
            if mt:
                return fn(mt)
        return None

    # -- configuration ----------------------------------------------------------------------------------------------
    def running(self, r: str) -> str:
        changed = self.lab.changed.get(r) if self.lab else None
        return render_running_config(self.cfg(r), changed, self.lab.changed_by.get(r, "lab") if self.lab else "lab")

    def running_if(self, r: str, raw: str) -> str:
        i = self.find_if(r, raw)
        if not i:
            return "                                                ^\n% Invalid input detected at '^' marker.\n"
        txt = section(render_running_config(self.cfg(r)), rf"^interface {re.escape(i.name)}$")
        return f"Building configuration...\n\nCurrent configuration : {len(txt)} bytes\n!\n{txt}end\n"

    def startup(self, r: str) -> str:
        text = self.lab.startup.get(r) if self.lab else None
        text = text or render_running_config(self.cfg(r))
        body = text.split("\n", 3)[3] if text.startswith("Building") else text
        return f"Using {len(body)} out of 522232 bytes\n{body}"

    # -- interfaces ---------------------------------------------------------------------------------------------------
    def interfaces(self, r: str, which: str | None) -> str:
        cfg = self.cfg(r)
        if which:
            i = self.find_if(r, which)
            if not i:
                return "                         ^\n% Invalid input detected at '^' marker.\n"
            ifs = [i]
        else:
            ifs = sorted(cfg.ifaces.values(), key=lambda i: if_sort_key(i.name))
        return "".join(self._interface(r, i) for i in ifs)

    def _counters(self, r: str, i: Iface) -> tuple[int, int, int, int]:
        t = max(self.uptime(), 1)
        if i.shutdown or i.name.startswith("Loopback"):
            return 0, 0, 0, 0
        rate = 0.35 if i.ospf_area is not None or i.v6_area is not None else 0.9 if i.vrf else 0.02
        pin = int(t * rate) + self.idx(r) * 7
        pout = int(t * rate * 0.97) + self.idx(r) * 5
        return pin, pin * 94, pout, pout * 92

    def _interface(self, r: str, i: Iface) -> str:
        up = self.line_up(r, i)
        state = "administratively down" if i.shutdown else "up"
        proto = "down" if i.shutdown else "up"
        lo = i.name.startswith("Loopback")
        hw = "Loopback" if lo else ("i82543 (Livengood)" if i.name.startswith("FastEthernet") else "AmdP2")
        lines = [f"{i.name} is {state}, line protocol is {proto} "]
        if lo:
            lines.append(f"  Hardware is {hw}")
        else:
            mac = self.mac(r, i.name)
            lines.append(f"  Hardware is {hw}, address is {mac} (bia {mac})")
        if i.description:
            lines.append(f"  Description: {i.description}")
        if i.ip:
            lines.append(f"  Internet address is {i.ip}/{_mask_bits(i.mask)}")
        bw = self.bw(i.name)
        delay = 5000 if lo else 100 if i.name.startswith("FastEthernet") else 1000
        mtu = 1514 if lo else 1500
        lines += [f"  MTU {mtu} bytes, BW {bw} Kbit/sec, DLY {delay} usec, ",
                  "     reliability 255/255, txload 1/255, rxload 1/255",
                  f"  Encapsulation {'LOOPBACK' if lo else 'ARPA'}, loopback not set"]
        if not lo:
            lines += ["  Keepalive set (10 sec)",
                      "  Full-duplex, 100Mb/s, 100BaseTX/FX" if i.name.startswith("FastEthernet") else "  Half-duplex, 10Mb/s",
                      "  ARP type: ARPA, ARP Timeout 04:00:00"]
        else:
            lines.append("  Keepalive set (10 sec)")
        pin, bin_, pout, bout = self._counters(r, i)
        last = "00:00:01" if up and not lo and pin else "never"
        lines += [f"  Last input {last}, output {'00:00:02' if up and not lo and pout else 'never'}, output hang never",
                  "  Last clearing of \"show interface\" counters never",
                  "  Input queue: 0/75/0/0 (size/max/drops/flushes); Total output drops: 0",
                  "  Queueing strategy: fifo",
                  "  Output queue: 0/40 (size/max)",
                  f"  5 minute input rate {0 if not pin else 1000} bits/sec, {0 if not pin else 1} packets/sec",
                  f"  5 minute output rate {0 if not pout else 1000} bits/sec, {0 if not pout else 1} packets/sec",
                  f"     {pin} packets input, {bin_} bytes, 0 no buffer",
                  f"     Received {pin // 9} broadcasts (0 IP multicasts)",
                  "     0 runts, 0 giants, 0 throttles",
                  "     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored",
                  "     0 watchdog",
                  "     0 input packets with dribble condition detected",
                  f"     {pout} packets output, {bout} bytes, 0 underruns",
                  "     0 output errors, 0 collisions, 0 interface resets",
                  "     0 unknown protocol drops",
                  "     0 babbles, 0 late collision, 0 deferred",
                  "     0 lost carrier, 0 no carrier",
                  "     0 output buffer failures, 0 output buffers swapped out"]
        return "\n".join(lines) + "\n"

    def if_description(self, r: str) -> str:
        rows = ["Interface                      Status         Protocol Description"]
        for i in sorted(self.cfg(r).ifaces.values(), key=lambda i: if_sort_key(i.name)):
            st = "admin down" if i.shutdown else "up"
            rows.append(f"{short_if(i.name):<30} {st:<14} {'down' if i.shutdown else 'up':<8} {i.description}")
        return "\n".join(rows) + "\n"

    def ip_interface(self, r: str, which: str | None) -> str:
        if which and which.lower() == "brief":
            return self.R.v4_if_brief(r)
        cfg = self.cfg(r)
        ifs = [self.find_if(r, which)] if which else sorted(cfg.ifaces.values(), key=lambda i: if_sort_key(i.name))
        if which and not ifs[0]:
            return "% Invalid input detected at '^' marker.\n"
        out = []
        for i in ifs:
            state, proto = ("administratively down", "down") if i.shutdown else ("up", "up")
            out.append(f"{i.name} is {state}, line protocol is {proto}")
            if not i.ip:
                out.append("  Internet protocol processing disabled")
                continue
            net = ipaddress.ip_interface(f"{i.ip}/{i.mask}")
            out += [f"  Internet address is {i.ip}/{net.network.prefixlen}",
                    f"  Broadcast address is 255.255.255.255",
                    "  Address determined by non-volatile memory",
                    f"  MTU is {i.mtu} bytes",
                    "  Helper address is not set",
                    "  Directed broadcast forwarding is disabled"]
            if i.ospf_area is not None:
                out.append("  Multicast reserved groups joined: 224.0.0.5 224.0.0.6")
            out += ["  Outgoing access list is not set", "  Inbound  access list is not set",
                    "  Proxy ARP is enabled", "  Local Proxy ARP is disabled", "  Security level is default",
                    "  Split horizon is enabled", "  ICMP redirects are always sent", "  ICMP unreachables are always sent",
                    "  ICMP mask replies are never sent", "  IP fast switching is enabled",
                    "  IP CEF switching is enabled", "  IP CEF switching turbo vector",
                    (f'  VPN Routing/Forwarding "{i.vrf}"' if i.vrf else "  IP multicast fast switching is enabled"),
                    "  Router Discovery is disabled", "  IP output packet accounting is disabled",
                    "  IP access violation accounting is disabled", "  TCP/IP header compression is disabled",
                    "  RTP/IP header compression is disabled", "  Policy routing is disabled",
                    "  Network address translation is disabled", "  BGP Policy Mapping is disabled",
                    "  Input features: MCI Check", "  IPv4 WCCP Redirect outbound is disabled",
                    "  IPv4 WCCP Redirect inbound is disabled", "  IPv4 WCCP Redirect exclude is disabled"]
        return "\n".join(out) + "\n"

    # -- routing ------------------------------------------------------------------------------------------------------
    def protocols(self, r: str) -> str:
        cfg = self.cfg(r)
        out = ["*** IP Routing is NSF aware ***", ""]
        if cfg.ospf:
            p = cfg.ospf
            rid = self.m.rid(r, "v4") or "0.0.0.0"
            areas = {i.ospf_area for i in cfg.ifaces.values() if i.ospf_area is not None}
            kinds = [p.area(a).kind for a in areas]
            redist = " ".join(f"{k}{' subnets' if v['subnets'] else ''}" for k, v in p.redistribute.items())
            out += [f'Routing Protocol is "ospf {p.pid}"',
                    "  Outgoing update filter list for all interfaces is not set",
                    "  Incoming update filter list for all interfaces is not set",
                    f"  Router ID {rid}"]
            if r in self.s.v4.abr:
                out.append("  It is an area border router")
            if r in self.s.v4.asbr:
                out.append("  It is an autonomous system boundary router")
                out.append(f"  Redistributing External Routes from,\n    {redist}")
            out += [f"  Number of areas in this router is {len(areas)}. {kinds.count('normal')} normal "
                    f"{kinds.count('stub')} stub {kinds.count('nssa')} nssa",
                    "  Maximum path: 4",
                    "  Routing for Networks:"]
            for a in sorted(areas):
                names = [i.name for i in sorted(cfg.ifaces.values(), key=lambda i: if_sort_key(i.name)) if i.ospf_area == a]
                out.append(f"  Routing on Interfaces Configured Explicitly (Area {a}):")
                out += [f"    {n}" for n in names]
            passive = [x.split(" ", 1)[1] for x in p.extra if x.startswith("passive-interface ")]
            if passive:
                out.append("  Passive Interface(s):")
                out += [f"    {ifname(x)}" for x in passive]
            out += ["  Routing Information Sources:", "    Gateway         Distance      Last Update"]
            seen = set()
            for n in self.s.v4.neighbors.get(r, []):
                if n.full and n.rid not in seen:
                    seen.add(n.rid)
                    out.append(f"    {n.rid:<15} {110:>8}      {self._age_short(('nbr', r, n.rid))}")
            out += ["  Distance: (default is 110)", ""]
        if cfg.ospf6 and cfg.v6_routing:
            out += [f'IPv6 Routing Protocol is "ospf {cfg.ospf6.pid}"', f"  Router ID {self.m.rid(r, 'v6') or '0.0.0.0'}",
                    "  Number of areas: "
                    f"{len({i.v6_area for i in cfg.ifaces.values() if i.v6_area is not None})}", ""]
        return "\n".join(out) + "\n"

    def _age_short(self, key) -> str:
        sec = int(self.uptime() % 3600)
        return f"{sec // 3600:02d}:{(sec // 60) % 60:02d}:{sec % 60:02d}"

    def route_summary(self, r: str) -> str:
        rib = self.R._rib(r, "v4")
        groups = {"connected": [x for x in rib if x.code in ("C", "L")], "static": [x for x in rib if x.code == "S"],
                  "ospf 1": [x for x in rib if x.code.startswith("O")]}
        out = ["IP routing table name is default (0x0)", "IP routing table maximum-paths is 32",
               "Route Source    Networks    Subnets     Replicates  Overhead    Memory (bytes)"]
        tot_n = tot_s = 0
        for name, rows in groups.items():
            nets = sum(1 for x in rows if x.prefix.prefixlen in (0, 8, 16, 24) and x.code != "L")
            subs = len(rows) - nets
            tot_n, tot_s = tot_n + nets, tot_s + subs
            out.append(f"{name:<15} {nets:<11} {subs:<11} {0:<11} {len(rows) * 72:<11} {len(rows) * 192}")
            if name == "ospf 1":
                kinds = [x.code for x in rows]
                intra = sum(1 for k in kinds if k == "O")
                inter = sum(1 for k in kinds if "IA" in k)
                ext = sum(1 for k in kinds if "E" in k)
                nssa = sum(1 for k in kinds if "N" in k)
                out.append(f"  Intra-area: {intra} Inter-area: {inter} External-1: 0 External-2: {ext}")
                out.append(f"  NSSA External-1: 0 NSSA External-2: {nssa}")
        out += ["internal        3                                                       1380",
                f"Total           {tot_n + 3:<11} {tot_s:<11} 0           {len(rib) * 72:<11} {len(rib) * 192 + 1380}"]
        return "\n".join(out) + "\n"

    def route_filtered(self, r: str, kind: str) -> str:
        code = {"connected": ("C",), "local": ("L",), "static": ("S",)}[kind]
        rows = [x for x in self.R._rib(r, "v4") if x.code in code]
        out = []
        for x in rows:
            out += self.R._route_lines(r, x, str(x.prefix), indent=False)
        return ("\n".join(out) + "\n") if out else ""

    def route_vrf(self, r: str, vrf: str) -> str:
        cfg = self.cfg(r)
        out = [f"\nRouting Table: {vrf}", "Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP",
               "       O - OSPF, IA - OSPF inter area", ""]
        ifs = [i for i in cfg.ifaces.values() if i.vrf == vrf and i.ip and not i.shutdown]
        default = next((s for s in cfg.statics if s[3] == vrf and s[0] == "0.0.0.0"), None)
        out.append(f"Gateway of last resort is {default[2]} to network 0.0.0.0\n" if default else "Gateway of last resort is not set\n")
        if default:
            out.append(f"S*    0.0.0.0/0 [1/0] via {default[2]}")
        for i in ifs:
            net = ipaddress.ip_interface(f"{i.ip}/{i.mask}").network
            out += [f"      {net.network_address}/8 is variably subnetted, 2 subnets, 2 masks",
                    f"C        {net} is directly connected, {i.name}",
                    f"L        {i.ip}/32 is directly connected, {i.name}"]
        return "\n".join(out) + "\n"

    def arp(self, r: str, vrf: str | None, all_vrfs: bool = False) -> str:
        cfg = self.cfg(r)
        rows = ["Protocol  Address          Age (min)  Hardware Addr   Type   Interface"]
        for i in sorted(cfg.ifaces.values(), key=lambda i: if_sort_key(i.name)):
            if not i.ip or i.shutdown or i.name.startswith("Loopback"):
                continue
            if not all_vrfs and (i.vrf or None) != (vrf or None):
                continue
            rows.append(f"Internet  {i.ip:<16} {'-':>9}  {self.mac(r, i.name)}  ARPA   {i.name}")
            for ifn, peer, pif in self.peers(r):
                if ifn != i.name:
                    continue
                pi = self.cfg(peer).ifaces.get(pif)
                if pi and pi.ip and not pi.shutdown:
                    rows.append(f"Internet  {pi.ip:<16} {int(self.uptime() // 60) % 4 or 1:>9}  {self.mac(peer, pif)}  ARPA   {i.name}")
            if i.vrf and i.ip.startswith("192.168.99."):
                gw = next((s[2] for s in cfg.statics if s[3] == i.vrf), None)
                if gw:
                    rows.append(f"Internet  {gw:<16} {2:>9}  0050.56c0.0001  ARPA   {i.name}")
        return "\n".join(rows) + "\n"

    def cdp(self, r: str, detail: bool) -> str:
        items = []
        for ifn, peer, pif in self.peers(r):
            mine, theirs = self.cfg(r).ifaces.get(ifn), self.cfg(peer).ifaces.get(pif)
            if mine and theirs and not mine.shutdown and not theirs.shutdown:
                items.append((ifn, peer, pif, theirs))
        if detail:
            out = []
            for ifn, peer, pif, theirs in items:
                out += ["-------------------------", f"Device ID: {self.cfg(peer).hostname}.lab.local", "Entry address(es): ",
                        f"  IP address: {theirs.ip}", "Platform: Cisco 7206VXR,  Capabilities: Router ",
                        f"Interface: {ifn},  Port ID (outgoing port): {pif}", "Holdtime : 151 sec", "",
                        "Version :", "Cisco IOS Software, 7200 Software (C7200-ADVENTERPRISEK9-M), Version 15.2(4)S6, RELEASE SOFTWARE (fc1)",
                        "", "advertisement version: 2", "Duplex: half", ""]
            return "\n".join(out) + (f"\nTotal cdp entries displayed : {len(items)}\n")
        out = ["Capability Codes: R - Router, T - Trans Bridge, B - Source Route Bridge",
               "                  S - Switch, H - Host, I - IGMP, r - Repeater, P - Phone, ",
               "                  D - Remote, C - CVTA, M - Two-port Mac Relay ", "",
               "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID"]
        for ifn, peer, pif, _ in items:
            out.append(f"{self.cfg(peer).hostname + '.lab.local':<16} {short_if(ifn):<17} {151:<10} {'R B':<11} {'7206VXR':<9} {short_if(pif)}")
        out.append(f"\nTotal cdp entries displayed : {len(items)}")
        return "\n".join(out) + "\n"

    def vrfs(self, r: str) -> str:
        cfg = self.cfg(r)
        rows = ["  Name                             Default RD            Interfaces"]
        for head, subs in cfg.blocks.items():
            m = re.fullmatch(r"ip vrf (\S+)", head)
            if not m:
                continue
            rd = next((x.split()[1] for x in subs if x.startswith("rd ")), "<not set>")
            ifs = [short_if(i.name) for i in cfg.ifaces.values() if i.vrf == m.group(1)]
            rows.append(f"  {m.group(1):<32} {rd:<21} {ifs[0] if ifs else ''}")
            rows += [f"  {'':<32} {'':<21} {x}" for x in ifs[1:]]
        return "\n".join(rows) + "\n"

    def cef(self, r: str, which: str | None) -> str:
        rows = ["Prefix               Next Hop             Interface",
                "0.0.0.0/0            no route",
                "0.0.0.0/8            drop",
                "127.0.0.0/8          drop"]
        rib = self.R._rib(r, "v4")
        for x in sorted(rib, key=lambda x: (int(x.prefix.network_address), x.prefix.prefixlen)):
            if x.prefix.prefixlen == 0:
                rows[1] = f"{'0.0.0.0/0':<20} {x.nexthops[0][0]:<20} {x.nexthops[0][1]}"
                continue
            if x.code == "L":
                rows.append(f"{str(x.prefix):<20} {'receive':<20} {x.nexthops[0][1]}")
            elif x.code == "C":
                rows.append(f"{str(x.prefix):<20} {'attached':<20} {x.nexthops[0][1]}")
            else:
                for k, (nh, ifn, _a) in enumerate(x.nexthops):
                    rows.append(f"{str(x.prefix) if k == 0 else '':<20} {nh:<20} {ifn}")
        rows += ["224.0.0.0/4          drop", "224.0.0.0/24         receive", "240.0.0.0/4          drop",
                 "255.255.255.255/32   receive"]
        if which:
            rows = [rows[0]] + [x for x in rows[1:] if x.startswith(which)]
        return "\n".join(rows) + "\n"

    def route_map(self, r: str, name: str | None) -> str:
        out = []
        for n, entries in self.cfg(r).route_maps.items():
            if name and n != name:
                continue
            for e in sorted(entries, key=lambda e: e["seq"]):
                out += [f"route-map {n}, {e['action']}, sequence {e['seq']}", "  Match clauses:"]
                if e["match_ifaces"]:
                    out.append(f"    interface {' '.join(e['match_ifaces'])} ")
                out += ["  Set clauses:", "  Policy routing matches: 0 packets, 0 bytes"]
        return "\n".join(out) + ("\n" if out else "")

    def hosts(self, r: str) -> str:
        dom = next((x.split()[-1] for x in self.cfg(r).misc if x.startswith("ip domain name")), "")
        return (f"Default domain is {dom or 'not set'}\nName/address lookup uses static mappings\n\n"
                "Codes: UN - unknown, EX - expired, OK - OK, ?? - revalidate\n"
                "       temp - temporary, perm - permanent\n       NA - Not Applicable None - Not defined\n\n"
                "Host                      Port  Flags      Age Type   Address(es)\n")

    # -- system -------------------------------------------------------------------------------------------------------
    def logging(self, r: str) -> str:
        logs = list(self.lab.logs.get(r, [])) if self.lab else []
        return ("Syslog logging: enabled (0 messages dropped, 0 messages rate-limited, 0 flushes, 0 overruns, xml disabled, filtering disabled)\n\n"
                "No Active Message Discriminator.\n\n\n\nNo Inactive Message Discriminator.\n\n\n"
                "    Console logging: level debugging, 0 messages logged, xml disabled,\n"
                "                     filtering disabled\n"
                "    Monitor logging: level debugging, 0 messages logged, xml disabled,\n"
                "                     filtering disabled\n"
                "    Buffer logging:  level debugging, "
                f"{len(logs)} messages logged, xml disabled,\n"
                "                    filtering disabled\n"
                "    Exception Logging: size (4096 bytes)\n"
                "    Count and timestamp logging messages: disabled\n"
                "    Persistent logging: disabled\n\n"
                "No active filter modules.\n\n"
                "    Trap logging: level informational, 0 message lines logged\n"
                "        Logging Source-Interface:       VRF Name:\n\n"
                f"Log Buffer (8192 bytes):\n\n" + "".join(x + "\n" for x in logs))

    def inventory(self, r: str) -> str:
        sn = f"4279{self.idx(r):04d}"
        return (f'NAME: "Chassis", DESCR: "Cisco 7206VXR, 6-slot chassis"\nPID: CISCO7206VXR      , VID:    , SN: {sn}\n\n'
                f'NAME: "NPE400 0", DESCR: "Cisco 7200VXR Network Processing Engine NPE-400"\nPID: NPE-400           , VID:    , SN: 1100{self.idx(r):04d}\n\n'
                f'NAME: "module 0", DESCR: "I/O FastEthernet (TX-ISL)"\nPID: C7200-IO-FE-MII/RJ45=, VID:    , SN: 4294{self.idx(r):04d}\n\n'
                f'NAME: "module 1", DESCR: "Ethernet 8 port"\nPID: PA-8E             , VID:    , SN: 7801{self.idx(r):04d}\n')

    def cpu(self) -> str:
        t = int(self.now)
        a, b = 1 + t % 3, t % 2
        rows = [f"CPU utilization for five seconds: {a}%/{b}%; one minute: 1%; five minutes: 1%",
                " PID Runtime(ms)     Invoked      uSecs   5Sec   1Min   5Min TTY Process "]
        procs = [(178, "OSPF-1 Hello"), (179, "OSPF-1 Router"), (150, "IP Input"), (62, "SSH Process"),
                 (1, "Chunk Manager"), (2, "Load Meter"), (98, "IP SLAs Event Processor"), (5, "Check heaps"),
                 (73, "ARP Input"), (140, "CDP Protocol")]
        up = max(int(self.uptime()), 1)
        for k, (pid, name) in enumerate(procs):
            inv = up // (k + 2) + 17
            rt = inv * (k % 3 + 1)
            rows.append(f"{pid:>4} {rt:>12} {inv:>12} {rt * 1000 // max(inv, 1):>10}  {'0.08' if k < 2 else '0.00':>5}%  "
                        f"{'0.02' if k < 2 else '0.00':>5}%  {'0.00':>5}%   0 {name}")
        return "\n".join(rows) + "\n"

    def memory(self) -> str:
        return ("                Head    Total(b)     Used(b)     Free(b)   Lowest(b)  Largest(b)\n"
                "Processor   66C8B8A0   190262624    61803212   128459412   127892880   127478236\n"
                "      I/O    EE00000    35651584     4890620    30760964    30738468    30750876\n")

    def flash(self) -> str:
        return ("Directory of disk0:/\n\n"
                f"    1  -rw-    40234504  Jun 21 2016 10:12:42 +00:00  {IMAGE}\n"
                "    2  -rw-        1803  Nov 15 2026 09:00:00 +00:00  vlan.dat\n\n"
                "128094208 bytes total (87853056 bytes free)\n")

    def lines(self, r: str) -> str:
        users = self.lab.sessions.get(r, []) if self.lab else []
        rows = ["   Tty Typ     Tx/Rx    A Modem  Roty AccO AccI   Uses   Noise  Overruns   Int",
                "*     0 CTY              -    -      -    -    -      0       0     0/0       -",
                "      1 AUX   9600/9600  -    -      -    -    -      0       0     0/0       -"]
        for k in range(5):
            mark = "*" if k < len(users) else " "
            rows.append(f"{mark}   {k + 2:>3} VTY              -    -      -    -    -  {k + 1 if k < len(users) else 0:>5}       0     0/0       -")
        return "\n".join(rows) + "\n"

    def tech(self, r: str) -> str:
        return ("\n------------------ show version ------------------\n\n" + self.R.version(r) +
                "\n------------------ show running-config ------------------\n\n" + self.running(r) +
                "\n------------------ show interfaces ------------------\n\n" + self.interfaces(r, None))

    # -- OSPF extras --------------------------------------------------------------------------------------------------
    def ospf_nbr_if(self, r: str, raw: str) -> str:
        if raw.lower() == "detail":
            return self.R.ospf_nbr_detail(r)
        name = ifname(raw)
        text = self.R.ospf_nbr(r, "v4")
        lines = text.splitlines()
        keep = [ln for ln in lines if ln.rstrip().endswith(name)]
        return "\n".join(lines[:3] + keep) + "\n" if keep else "\n".join(lines[:3]) + "\n"

    def ospf_stats(self, r: str) -> str:
        rid = self.m.rid(r, "v4") or "0.0.0.0"
        n = 3 + int(self.uptime() // 600)
        areas = sorted({i.ospf_area for i in self.cfg(r).ifaces.values() if i.ospf_area is not None})
        out = [f"\n            OSPF Router with ID ({rid}) (Process ID 1)\n"]
        for a in areas:
            out.append(f"  Area {a}: SPF algorithm executed {n} times")
        out += ["", "  Summary OSPF SPF statistic", "", "  SPF calculation time",
                "Delta T   Intra D-Intra Summ    D-Summ  Ext     D-Ext   Total   Reason",
                "00:00:12  0       0       0       0       0       0       0       R, N, SN"]
        return "\n".join(out) + "\n"

    def ospf_traffic(self, r: str) -> str:
        t = max(int(self.uptime()), 1)
        hello = t // 10 * max(len(self.s.v4.ifstates.get(r, [])), 1)
        return (f"\nOSPF statistics:\n  Last clearing of OSPF traffic counters never\n  Rcvd: {hello + 40} total, 0 checksum errors\n"
                f"    {hello} hello, 8 database desc, 2 link state req\n    18 link state updates, 12 link state acks\n\n"
                f"  Sent: {hello + 44} total\n    {hello} hello, 10 database desc, 2 link state req\n"
                "    20 link state updates, 12 link state acks\n")

    def ospf_events(self, r: str) -> str:
        logs = list(self.lab.logs.get(r, [])) if self.lab else []
        ev = [x for x in logs if "OSPF" in x]
        return "\n            OSPF Router with ID ({}) (Process ID 1)\n\n".format(self.m.rid(r, "v4") or "0.0.0.0") + \
            "".join(f"{k + 1}  {x}\n" for k, x in enumerate(reversed(ev[-20:])))

    def ospf_rib(self, r: str) -> str:
        rid = self.m.rid(r, "v4") or "0.0.0.0"
        out = [f"\n            OSPF Router with ID ({rid}) (Process ID 1)\n", "\n                Base Topology (MTID 0)\n",
               "OSPF local RIB", "Codes: * - Best, > - Installed in global RIB", ""]
        for x in self.R._rib(r, "v4"):
            if not x.code.startswith("O"):
                continue
            out.append(f"*>  {x.prefix}, {x.kind or 'Intra'}, cost {x.metric}, area {0}")
            for nh, ifn, adv in x.nexthops:
                out.append(f"      via {nh}, {ifn}")
        return "\n".join(out) + "\n"

    def ospf_db_summary(self, r: str) -> str:
        lsdb = self.s.v4.lsdb
        rid = self.m.rid(r, "v4") or "0.0.0.0"
        out = [f"\n            OSPF Router with ID ({rid}) (Process ID 1)\n"]
        areas = sorted({x.area for x in lsdb if x.area is not None})
        for a in areas:
            rows = [x for x in lsdb if x.area == a]
            cnt = lambda t: sum(1 for x in rows if x.ltype == t)  # noqa: E731
            out += [f"Area {a} database summary", "  LSA Type      Count    Delete   Maxage",
                    f"  Router        {cnt('router'):<8} 0        0", f"  Network       {cnt('network'):<8} 0        0",
                    f"  Summary Net   {cnt('summary'):<8} 0        0", f"  Summary ASBR  {cnt('asbr-summary'):<8} 0        0",
                    f"  Type-7 Ext    {cnt('nssa'):<8} 0        0", f"  Subtotal      {len(rows):<8} 0        0", ""]
        ext = sum(1 for x in lsdb if x.ltype == "external")
        out += ["Process 1 database summary", f"  Type-5 Ext    {ext:<8} 0        0", f"  Total         {len(lsdb):<8} 0        0"]
        return "\n".join(out) + "\n"

    def sla_summary(self, r: str) -> str:
        cfg = self.cfg(r)
        if not cfg.sla:
            return ""
        out = ["IPSLAs Latest Operation Summary", "Codes: * active, ^ inactive, ~ pending", "",
               "ID           Type        Destination       Stats       Return      Last",
               "                                             (ms)        Code        Run ",
               "-----------------------------------------------------------------------"]
        text = self.R.sla(r)
        ok = "Return Code: OK" in text
        rtt = re.search(r"Latest RTT: (\d+)", text)
        for sid, op in sorted(cfg.sla.items()):
            mark = "*" if sid in cfg.sla_scheduled else "^"
            out.append(f"{mark}{sid:<11} {op.get('type') or 'icmp-echo':<11} {op.get('target') or '-':<17} "
                       f"RTT={rtt.group(1) if rtt and ok else '-':<7} {'OK' if ok else 'Timeout':<11} 3 seconds ago")
        return "\n".join(out) + "\n"

    def sla_config(self, r: str) -> str:
        out = []
        for sid, op in sorted(self.cfg(r).sla.items()):
            out += ["IP SLAs Infrastructure Engine-III", f"Entry number: {sid}", "Owner: ", "Tag: ",
                    f"Operation timeout (milliseconds): 5000", f"Type of operation to perform: {op.get('type') or 'icmp-echo'}",
                    f"Target address/Source interface: {op.get('target')}/{op.get('source') or ''}",
                    "Type Of Service parameter: 0x0", "Request size (ARR data portion): 28",
                    "Verify data: No", "Vrf Name: ", "Schedule:",
                    "   Operation frequency (seconds): " + str(op.get("frequency", 60)) + "  (not considered if randomly scheduled)",
                    "   Next Scheduled Start Time: Start Time already passed",
                    "   Group Scheduled : FALSE", "   Randomly Scheduled : FALSE",
                    "   Life (seconds): Forever", "   Entry Ageout (seconds): never",
                    "   Recurring (Starting Everyday): FALSE",
                    f"   Status of entry (SNMP RowStatus): {'Active' if sid in self.cfg(r).sla_scheduled else 'notInService'}",
                    "Threshold (milliseconds): 5000", ""]
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------------------
# ping / traceroute over the simulated routing tables
def _owner(model, addr: ipaddress.IPv4Address) -> tuple[str, Iface] | None:
    for r, cfg in model.configs.items():
        for i in cfg.ifaces.values():
            if i.ip and not i.vrf and ipaddress.ip_address(i.ip) == addr:
                return r, i
    return None


def _lookup(snap, r: str, addr):
    cands = [x for x in snap.v4.routes.get(r, []) if addr in x.prefix]
    return max(cands, key=lambda x: (x.prefix.prefixlen, -x.ad)) if cands else None


def path(model, snap, src: str, dest: str, limit: int = 15) -> tuple[list[str], bool]:
    """Hop addresses from src toward dest (the interface each hop answers from) and whether dest answers."""
    try:
        addr = ipaddress.ip_address(dest)
    except ValueError:
        return [], False
    hops, cur = [], src
    owner = _owner(model, addr)
    for _ in range(limit):
        cfg = model.configs[cur]
        if any(i.ip and not i.vrf and not i.shutdown and ipaddress.ip_address(i.ip) == addr for i in cfg.ifaces.values()):
            return hops, True
        rt = _lookup(snap, cur, addr)
        if not rt:
            return hops, False
        if rt.code in ("C", "L"):
            # directly connected: it answers if a router owns the address and that interface is up
            if owner and not owner[1].shutdown:
                hops.append(dest)
                return hops, True
            return hops, False
        nh = rt.nexthops[0][0]
        try:
            nxt = _owner(model, ipaddress.ip_address(nh))
        except ValueError:
            return hops, False
        if not nxt:
            return hops, False
        hops.append(nh)
        cur = nxt[0]
        if owner and cur == owner[0]:
            hops[-1] = dest          # the last hop answers from the destination address itself
            return hops, True
    return hops, False


def ping(model, snap, src: str, dest: str, count: int = 5, size: int = 100) -> str:
    try:
        ipaddress.ip_address(dest)
    except ValueError:
        return f"% Unrecognized host or address, or protocol not running.\n"
    hops, ok = path(model, snap, src, dest)
    # the reply must find its way back too
    if ok and hops:
        owner = _owner(model, ipaddress.ip_address(dest))
        src_if = next((i for i in model.configs[src].ifaces.values() if i.ip and not i.vrf and not i.shutdown), None)
        if owner and src_if:
            back = _lookup(snap, owner[0], ipaddress.ip_address(src_if.ip))
            ok = back is not None
    marks = ("!" if ok else ".") * count
    out = ["Type escape sequence to abort.",
           f"Sending {count}, {size}-byte ICMP Echos to {dest}, timeout is 2 seconds:", marks]
    if ok:
        n = len(hops) or 1
        out.append(f"Success rate is 100 percent ({count}/{count}), round-trip min/avg/max = {n * 4}/{n * 9}/{n * 16} ms")
    else:
        out.append(f"Success rate is 0 percent (0/{count})")
    return "\n".join(out) + "\n"


def traceroute(model, snap, src: str, dest: str) -> str:
    try:
        ipaddress.ip_address(dest)
    except ValueError:
        return "% Unrecognized host or address, or protocol not running.\n"
    hops, ok = path(model, snap, src, dest)
    out = ["Type escape sequence to abort.", f"Tracing the route to {dest}", "VRF info: (vrf in name/id, vrf out name/id)"]
    for k, h in enumerate(hops, 1):
        out.append(f"  {k} {h} {k * 8} msec {k * 9} msec {k * 7} msec")
    if not ok:
        for k in range(len(hops) + 1, len(hops) + 4):
            out.append(f"  {k}  *  *  * ")
    return "\n".join(out) + "\n"
