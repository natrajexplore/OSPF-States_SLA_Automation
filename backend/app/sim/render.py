"""IOS-format output of the `show` commands the scenarios, the monitor and the CLI tab use."""
from __future__ import annotations

import ipaddress
import re
import time

from .iosconfig import ifname, render_ospf_section, short_if
from .ospf import Model, Route, Snapshot

_ROUTE_CODES_V4 = """Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area
       N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
       E1 - OSPF external type 1, E2 - OSPF external type 2
       i - IS-IS, su - IS-IS summary, L1 - IS-IS level-1, L2 - IS-IS level-2
       ia - IS-IS inter area, * - candidate default, U - per-user static route
       o - ODR, P - periodic downloaded static route, H - NHRP, l - LISP
       + - replicated route, % - next hop override
"""
_ROUTE_CODES_V6 = """Codes: C - Connected, L - Local, S - Static, U - Per-user Static route
       B - BGP, R - RIP, H - NHRP, I1 - ISIS L1
       I2 - ISIS L2, IA - ISIS interarea, IS - ISIS summary, D - EIGRP
       EX - EIGRP external, ND - ND Default, NDp - ND Prefix, DCE - Destination
       NDr - Redirect, O - OSPF Intra, OI - OSPF Inter, OE1 - OSPF ext 1
       OE2 - OSPF ext 2, ON1 - OSPF NSSA ext 1, ON2 - OSPF NSSA ext 2
       l - LISP"""

INVALID = "% Invalid input detected at '^' marker.\n"


def _more(renderer):
    from .iosshow import IosShow
    return IosShow(renderer)


def _hms(sec: float) -> str:
    sec = max(0, int(sec))
    if sec >= 86400:
        return f"{sec // 86400}d{(sec % 86400) // 3600:02d}h"
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


class Renderer:
    def __init__(self, model: Model, snap: Snapshot, now: float, born: dict, started: float) -> None:
        self.m, self.s, self.now, self.born, self.started = model, snap, now, born, started

    def age(self, key) -> float:
        return self.now - self.born.setdefault(key, self.now)

    # ------------------------------------------------------------------------------------------------------------
    def show(self, r: str, cmd: str) -> str:
        c = " ".join(cmd.split())
        table = [
            (r"show ip ospf database database-summary", lambda m: _more(self).ospf_db_summary(r)),
            (r"show ip ospf neighbor", lambda m: self.ospf_nbr(r, "v4")),
            (r"show ip ospf neighbor detail", lambda m: self.ospf_nbr_detail(r)),
            (r"show ip ospf interface brief", lambda m: self.ospf_if_brief(r, "v4")),
            (r"show ip ospf interface(?: (\S+))?", lambda m: self.ospf_if(r, "v4", m.group(1))),
            (r"show ip ospf database(?: (\S+))?(?: (\S+))?", lambda m: self.ospf_db(r, m.group(1), m.group(2))),
            (r"show ip ospf border-routers", lambda m: self.border(r)),
            (r"show ip ospf", lambda m: self.ospf_proc(r, "v4")),
            (r"show ip route ospf", lambda m: self.route_table(r, "v4", ospf_only=True)),
            (r"show ip route", lambda m: self.route_table(r, "v4", ospf_only=False)),
            (r"show ip route (\d+\.\d+\.\d+\.\d+)(?: (\d+\.\d+\.\d+\.\d+))?", lambda m: self.route_lookup(r, m.group(1))),
            (r"show bfd neighbors(?: details?)?", lambda m: self.bfd(r)),
            (r"show ip sla statistics(?: \d+)?", lambda m: self.sla(r)),
            (r"show running-config \| section ipv6 router ospf", lambda m: render_ospf_section(self.m.configs[r], v6=True)),
            (r"show running-config \| section router ospf", lambda m: render_ospf_section(self.m.configs[r])),
            (r"show ipv6 ospf neighbor(?: detail)?", lambda m: self.ospf_nbr(r, "v6")),
            (r"show ipv6 ospf interface brief", lambda m: self.ospf_if_brief(r, "v6")),
            (r"show ipv6 ospf interface(?: (\S+))?", lambda m: self.ospf_if(r, "v6", m.group(1))),
            (r"show ipv6 ospf(?: database(?: \S+)?| border-routers)?", lambda m: self.ospf_proc(r, "v6")),
            (r"show ipv6 route ospf", lambda m: self.route_table(r, "v6", ospf_only=True)),
            (r"show ipv6 route", lambda m: self.route_table(r, "v6", ospf_only=False)),
            (r"show ipv6 route ([0-9a-fA-F:]+(?:/\d+)?)", lambda m: self.route_table(r, "v6", ospf_only=False, only=m.group(1))),
            (r"show ipv6 interface brief", lambda m: self.v6_if_brief(r)),
            (r"show ip interface brief", lambda m: self.v4_if_brief(r)),
            (r"show clock", lambda m: time.strftime("*%H:%M:%S.000 UTC %a %b %d %Y", time.gmtime(self.now))),
            (r"show version", lambda m: self.version(r)),
        ]
        for pat, fn in table:
            mt = re.fullmatch(pat, c, re.IGNORECASE)
            if mt:
                return fn(mt)
        from .iosshow import IosShow
        more = IosShow(self).show(r, c)
        return INVALID if more is None else more

    # -- neighbors ------------------------------------------------------------------------------------------------
    def _dead(self, r: str, iface: str, af: str) -> str:
        st = next((x for x in self.s.__dict__[af].ifstates[r] if x.iface == iface), None)
        if st and st.dead == 1:
            return f"{int(400 + (self.now * 1000) % 600)} msec"
        dead = st.dead if st else 40
        hello = (st.hello_ms // 1000) if st else 10
        return _hms(dead - (int(self.now) % max(1, hello)))

    def ospf_nbr(self, r: str, af: str) -> str:
        view = self.s.v4 if af == "v4" else self.s.v6
        cfg = self.m.configs[r]
        if (cfg.ospf if af == "v4" else cfg.ospf6) is None:
            return ""
        nbrs = view.neighbors[r]
        rows = []
        for n in sorted(nbrs, key=lambda n: (n.iface, ipaddress.ip_address(n.rid))):
            state = f"{n.state}/{'  -' if n.role == '-' else n.role}"
            dead = self._dead(r, n.iface, af)
            if af == "v4":
                rows.append(f"{n.rid:<15} {n.priority:>3}   {state:<15} {dead:<11} {n.address:<15} {n.iface}")
            else:
                rows.append(f"{n.rid:<15} {n.priority:>3}   {state:<15} {dead:<11} {n.intf_id:<15} {n.iface}")
        if af == "v4":
            head = "\nNeighbor ID     Pri   State           Dead Time   Address         Interface"
            return head + ("\n" + "\n".join(rows) if rows else "") + "\n"
        rid = self.m.rid(r, "v6")
        head = (f"\n            OSPFv3 Router with ID ({rid}) (Process ID {cfg.ospf6.pid})\n\n"
                "Neighbor ID     Pri   State           Dead Time   Interface ID    Interface")
        return head + ("\n" + "\n".join(rows) if rows else "") + "\n"

    def ospf_nbr_detail(self, r: str) -> str:
        out = []
        for n in self.s.v4.neighbors[r]:
            st = next((x for x in self.s.v4.ifstates[r] if x.iface == n.iface), None)
            out.append(f" Neighbor {n.rid}, interface address {n.address}\n"
                       f"    In the area {st.area if st else 0} via interface {n.iface}\n"
                       f"    Neighbor priority is {n.priority}, State is {n.state}, 6 state changes\n"
                       f"    DR is {st.dr[1] if st and st.dr else '0.0.0.0'} BDR is {st.bdr[1] if st and st.bdr else '0.0.0.0'}\n"
                       f"    Options is 0x12 in Hello (E-bit, L-bit)\n"
                       f"    Dead timer due in {self._dead(r, n.iface, 'v4')}\n"
                       f"    Neighbor is up for {_hms(self.age(('nbr', r, n.rid)))}\n")
        return "\n".join(out)

    # -- interfaces -----------------------------------------------------------------------------------------------
    _BRIEF_STATE = {"DR": "DR", "BDR": "BDR", "DROTHER": "DROTH", "POINT_TO_POINT": "P2P", "LOOPBACK": "LOOP",
                    "WAITING": "WAIT"}

    def ospf_if_brief(self, r: str, af: str) -> str:
        view = self.s.v4 if af == "v4" else self.s.v6
        nb = view.neighbors[r]
        if af == "v4":
            rows = ["Interface    PID   Area            IP Address/Mask    Cost  State Nbrs F/C"]
        else:
            rows = ["Interface    PID   Area            Intf ID    Cost  State Nbrs F/C"]
        for st in view.ifstates[r]:
            mine = [n for n in nb if n.iface == st.iface]
            fc = f"{sum(n.full for n in mine)}/{len(mine)}"
            state = self._BRIEF_STATE.get(st.state, st.state)
            if af == "v4":
                rows.append(f"{short_if(st.iface):<12} 1     {st.area:<15} {st.address:<18} {st.cost:<5} {state:<5} {fc}")
            else:
                rows.append(f"{short_if(st.iface):<12} 1     {st.area:<15} {self.m.intf_id(st.iface):<10} {st.cost:<5} {state:<5} {fc}")
        return "\n".join(rows) + "\n"

    def ospf_if(self, r: str, af: str, which: str | None) -> str:
        view = self.s.v4 if af == "v4" else self.s.v6
        rid = self.m.rid(r, af)
        want = ifname(which) if which else None
        if want and want not in self.m.configs[r].ifaces:
            return INVALID
        out = []
        for st in view.ifstates[r]:
            if want and st.iface != want:
                continue
            nb = [n for n in view.neighbors[r] if n.iface == st.iface]
            full = [n for n in nb if n.full]
            hello = f"{st.hello_ms} msec" if st.hello_ms < 1000 else str(st.hello_ms // 1000)
            lines = [f"{st.iface} is up, line protocol is up "]
            if af == "v4":
                lines += [f"  Internet Address {st.address}, Area {st.area}, Attached via Interface Enable",
                          f"  Process ID 1, Router ID {rid}, Network Type {st.net_type}, Cost: {st.cost}",
                          "  Topology-MTID    Cost    Disabled    Shutdown      Topology Name",
                          f"        0           {st.cost:<6}    no          no            Base",
                          "  Enabled by interface config, including secondary ip addresses"]
            else:
                lines += [f"  Link Local Address {self.m.link_local(r, self.m.configs[r].ifaces[st.iface])}, Interface ID {self.m.intf_id(st.iface)}",
                          f"  Area {st.area}, Process ID 1, Instance ID {st.instance}, Router ID {rid}",
                          f"  Network Type {st.net_type}, Cost: {st.cost}"]
            if st.net_type == "LOOPBACK":
                lines.append("  Loopback interface is treated as a stub Host")
                out.append("\n".join(lines))
                continue
            state = st.state if st.net_type == "BROADCAST" else "POINT_TO_POINT"
            prio = f", Priority {st.priority}" if st.net_type == "BROADCAST" else ""
            lines.append(f"  Transmit Delay is 1 sec, State {state}{prio}")
            if st.net_type == "BROADCAST":
                if st.dr:
                    lines.append(f"  Designated Router (ID) {st.dr[0]}, Interface address {st.dr[1]}")
                if st.bdr:
                    lines.append(f"  Backup Designated router (ID) {st.bdr[0]}, Interface address {st.bdr[1]}")
            lines += [f"  Timer intervals configured, Hello {hello}, Dead {st.dead}, Wait {st.dead}, Retransmit 5",
                      "    oob-resync timeout 40",
                      f"    Hello due in {'00:00:00' if st.hello_ms < 1000 else _hms(st.hello_ms // 1000 - int(self.now) % max(1, st.hello_ms // 1000))}"]
            if st.bfd:
                lines.append("  BFD enabled")
            lines += ["  Supports Link-local Signaling (LLS)", "  Cisco NSF helper support enabled",
                      "  IETF NSF helper support enabled", "  Index 1/1, flood queue length 0",
                      "  Next 0x0(0)/0x0(0)", "  Last flood scan length is 1, maximum is 3",
                      "  Last flood scan time is 0 msec, maximum is 4 msec",
                      f"  Neighbor Count is {len(nb)}, Adjacent neighbor count is {len(full)} "]
            for n in full:
                tag = {"DR": "  (Designated Router)", "BDR": "  (Backup Designated Router)"}.get(n.role, "")
                lines.append(f"    Adjacent with neighbor {n.rid}{tag}")
            lines.append("  Suppress hello for 0 neighbor(s)")
            out.append("\n".join(lines))
        return "\n".join(out) + ("\n" if out else "")

    def v4_if_brief(self, r: str) -> str:
        rows = ["Interface                  IP-Address      OK? Method Status                Protocol"]
        for i in sorted(self.m.configs[r].ifaces.values(), key=_brief_order):
            st = "administratively down" if i.shutdown else "up"
            rows.append(f"{i.name:<26} {i.ip or 'unassigned':<15} YES {'NVRAM' if i.ip else 'unset':<6} {st:<21} {'down' if i.shutdown else 'up'}")
        return "\n".join(rows) + "\n"

    def v6_if_brief(self, r: str) -> str:
        cfg = self.m.configs[r]
        rows = []
        for i in sorted(cfg.ifaces.values(), key=_brief_order):
            rows.append(f"{i.name:<26} [{'administratively down' if i.shutdown else 'up'}/{'down' if i.shutdown else 'up'}]")
            if i.v6_addrs:
                rows.append(f"    {self.m.link_local(r, i)}")
                rows += [f"    {str(ipaddress.ip_interface(a).ip).upper()}" for a in i.v6_addrs]
            else:
                rows.append("    unassigned")
        return "\n".join(rows) + "\n"

    # -- process / LSDB ---------------------------------------------------------------------------------------------
    def ospf_proc(self, r: str, af: str) -> str:
        cfg = self.m.configs[r]
        proc = cfg.ospf if af == "v4" else cfg.ospf6
        if proc is None:
            return "" if af == "v6" else "%OSPF: Router process 1 is not running, please configure a router-id\n"
        view = self.s.v4 if af == "v4" else self.s.v6
        rid = self.m.rid(r, af)
        areas = sorted({st.area for st in view.ifstates[r]})
        kinds = [proc.area(a).kind for a in areas]
        nlsa5 = sum(1 for lsa in view.lsdb if lsa.ltype == "external")
        lines = [f" Routing Process \"{'ospfv3' if af == 'v6' else 'ospf'} {proc.pid}\" with ID {rid}",
                 f" Start time: 00:00:41.692, Time elapsed: {_hms(self.now - self.started)}.120",
                 " Supports only single TOS(TOS0) routes", " Supports opaque LSA",
                 " Supports Link-local Signaling (LLS)", " Supports area transit capability",
                 " Supports NSSA (compatible with RFC 3101)",
                 " Event-log enabled, Maximum number of events: 1000, Mode: cyclic"]
        if r in view.abr:
            lines.append(" It is an area border router")
        if r in view.asbr:
            lines.append(" It is an autonomous system boundary router")
            lines.append(" Redistributing External Routes from,")
            for src in proc.redistribute:
                lines.append(f"    {src}{', includes subnets in redistribution' if proc.redistribute[src]['subnets'] else ''}")
        lines += [" Router is not originating router-LSAs with maximum metric",
                  " Initial SPF schedule delay 5000 msecs",
                  " Minimum hold time between two consecutive SPFs 10000 msecs",
                  " Maximum wait time between two consecutive SPFs 10000 msecs",
                  " Incremental-SPF disabled", " Minimum LSA interval 5 secs", " Minimum LSA arrival 1000 msecs",
                  " LSA group pacing timer 240 secs", " Interface flood pacing timer 33 msecs",
                  " Retransmission pacing timer 66 msecs",
                  f" Number of external LSA {nlsa5}. Checksum Sum 0x{(nlsa5 * 0x1F3A7) & 0xFFFFFF:06X}",
                  " Number of opaque AS LSA 0. Checksum Sum 0x000000",
                  " Number of DCbitless external and opaque AS LSA 0",
                  " Number of DoNotAge external and opaque AS LSA 0",
                  f" Number of areas in this router is {len(areas)}. {kinds.count('normal')} normal "
                  f"{kinds.count('stub')} stub {kinds.count('nssa')} nssa",
                  " Number of areas transit capable is 0", " External flood list length 0",
                  " IETF NSF helper support enabled", " Cisco NSF helper support enabled",
                  f" Reference bandwidth unit is {proc.ref_bw} mbps"]
        for a in areas:
            sts = [st for st in view.ifstates[r] if st.area == a]
            loops = sum(1 for st in sts if st.net_type == "LOOPBACK")
            kind = proc.area(a)
            lines.append(f"    Area {'BACKBONE(0)' if a == 0 else a}")
            lines.append(f"        Number of interfaces in this area is {len(sts)}{f' ({loops} loopback)' if loops else ''}")
            if kind.kind == "stub":
                lines.append(f"        It is a stub area{', no summary LSA in this area' if kind.no_summary else ''}")
                if r in view.abr:
                    lines.append("          generates stub default route with cost 1")
            elif kind.kind == "nssa":
                lines.append("        It is a NSSA area")
                if r in view.abr:
                    lines.append(f"        Perform type-7/type-5 LSA translation{' (always)' if kind.translate_always else ''}")
            nl = sum(1 for lsa in view.lsdb if lsa.area == a)
            lines += ["        Area has no authentication",
                      f"        SPF algorithm last executed {_hms(self.age(('spf', r, a)))}.120 ago",
                      f"        SPF algorithm executed {4 + len(self.born) % 9} times", "        Area ranges are",
                      f"        Number of LSA {nl}. Checksum Sum 0x{(nl * 0x2B5C1) & 0xFFFFFF:06X}",
                      "        Number of opaque link LSA 0. Checksum Sum 0x000000",
                      "        Number of DCbitless LSA 0", "        Number of indication LSA 0",
                      "        Number of DoNotAge LSA 0", "        Flood list length 0"]
        return "\n".join(lines) + "\n"

    def _lsa_line(self, lsa, extra: str = "") -> str:
        age = int(self.age(("lsa", lsa.ltype, lsa.lsid, lsa.adv, lsa.area))) % 1800
        seq = 0x80000001 + (hash((lsa.ltype, lsa.lsid, lsa.adv)) % 7)
        ck = (hash((lsa.lsid, lsa.adv, lsa.ltype)) & 0xFFFF)
        return f"{lsa.lsid:<15} {lsa.adv:<15} {age:<8} 0x{seq:08X} 0x{ck:06X} {extra}".rstrip()

    def ospf_db(self, r: str, kind: str | None, lsid: str | None) -> str:
        cfg = self.m.configs[r]
        if cfg.ospf is None:
            return ""
        view = self.s.v4
        rid = self.m.rid(r, "v4")
        my_areas = sorted({st.area for st in view.ifstates[r]})
        sees5 = any(cfg.ospf.area(a).kind == "normal" for a in my_areas)
        head = f"\n            OSPF Router with ID ({rid}) (Process ID {cfg.ospf.pid})\n"
        kind = (kind or "").lower()
        if kind == "":
            out = [head]
            for a in my_areas:
                for lt, title in (("router", "Router Link States"), ("network", "Net Link States"),
                                  ("summary", "Summary Net Link States"), ("nssa", "Type-7 AS External Link States")):
                    lsas = [x for x in view.lsdb if x.ltype == lt and x.area == a]
                    if not lsas:
                        continue
                    hdr = "Link ID         ADV Router      Age         Seq#       Checksum"
                    hdr += " Link count" if lt == "router" else " Tag" if lt == "nssa" else ""
                    out.append(f"\n                {title} (Area {a})\n\n{hdr}")
                    for x in sorted(lsas, key=lambda x: (ipaddress.ip_address(x.lsid), x.adv)):
                        out.append(self._lsa_line(x, str(x.extra.get("links", "")) if lt == "router" else "0" if lt == "nssa" else ""))
            ext = [x for x in view.lsdb if x.ltype == "external"] if sees5 else []
            if ext:
                out.append("\n                Type-5 AS External Link States\n\n"
                           "Link ID         ADV Router      Age         Seq#       Checksum Tag")
                for x in sorted(ext, key=lambda x: (ipaddress.ip_address(x.lsid), x.adv)):
                    out.append(self._lsa_line(x, "0"))
            return "\n".join(out) + "\n"

        ltype = {"summary": "summary", "external": "external", "nssa-external": "nssa", "router": "router",
                 "network": "network"}.get(kind)
        if ltype is None:
            return INVALID
        lsas = [x for x in view.lsdb if x.ltype == ltype and (x.area in my_areas or (ltype == "external" and sees5))
                and (lsid is None or x.lsid == lsid)]
        out = [head]
        title = {"summary": "Summary Net Link States", "external": "Type-5 AS External Link States",
                 "nssa": "Type-7 AS External Link States", "router": "Router Link States",
                 "network": "Net Link States"}[ltype]
        groups: dict = {}
        for x in lsas:
            groups.setdefault(x.area, []).append(x)
        for area, items in sorted(groups.items(), key=lambda kv: -1 if kv[0] is None else kv[0]):
            out.append(f"\n                {title}{'' if area is None else f' (Area {area})'}\n")
            for x in sorted(items, key=lambda x: (ipaddress.ip_address(x.lsid), x.adv)):
                age = int(self.age(("lsa", x.ltype, x.lsid, x.adv, x.area))) % 1800
                blk = [f"  LS age: {age}", "  Options: (No TOS-capability, DC, Upward)"]
                if ltype == "summary":
                    blk += ["  LS Type: Summary Links(Network)", f"  Link State ID: {x.lsid} (summary Network Number)",
                            f"  Advertising Router: {x.adv}", "  LS Seq Number: 80000001", "  Checksum: 0x5A2B",
                            "  Length: 28", f"  Network Mask: /{x.mask}", f"        MTID: 0         Metric: {x.metric} "]
                elif ltype in ("external", "nssa"):
                    blk += [f"  LS Type: {'AS External Link' if ltype == 'external' else 'AS External Link (NSSA)'}",
                            f"  Link State ID: {x.lsid} (External Network Number )",
                            f"  Advertising Router: {x.adv}", "  LS Seq Number: 80000001", "  Checksum: 0x7C11",
                            "  Length: 36", f"  Network Mask: /{x.mask}",
                            f"        Metric Type: {x.mtype} (Larger than any link state path)",
                            "        MTID: 0 ", f"        Metric: {x.metric} ", "        Forward Address: 0.0.0.0",
                            "        External Route Tag: 0"]
                elif ltype == "router":
                    blk += ["  LS Type: Router Links", f"  Link State ID: {x.lsid}", f"  Advertising Router: {x.adv}",
                            f"  Number of Links: {x.extra.get('links', 0)}"]
                else:
                    blk += ["  LS Type: Network Links", f"  Link State ID: {x.lsid} (address of Designated Router)",
                            f"  Advertising Router: {x.adv}", f"  Network Mask: /{x.mask}"]
                out.append("\n".join(blk) + "\n")
        return "\n".join(out) + "\n"

    def border(self, r: str) -> str:
        rr = self.s.v4.router_routes.get(r, [])
        rid = self.m.rid(r, "v4")
        out = [f"\n            OSPF Router with ID ({rid}) (Process ID 1)\n\n\n\t\tBase Topology (MTID 0)\n",
               "Internal Router Routing Table", "Codes: i - Intra-area route, I - Inter-area route\n"]
        for t in rr:
            for nh, ifn in t[2] or [("", "")]:
                out.append(f"{t[3]} {t[0]} [{t[1]}] via {nh}, {ifn}, {t[5]}, Area {t[4]}, SPF 7")
        return "\n".join(out) + "\n"

    # -- routing table ----------------------------------------------------------------------------------------------
    def _rib(self, r: str, af: str) -> list[Route]:
        return (self.s.v4 if af == "v4" else self.s.v6).routes.get(r, [])

    def route_table(self, r: str, af: str, ospf_only: bool, only: str | None = None) -> str:
        rib = self._rib(r, af)
        if af == "v6":
            if not self.m.configs[r].v6_routing:
                return "% IPv6 routing not enabled\n" if not ospf_only else _v6_header(0)
            rows = [x for x in rib if not ospf_only or x.code.startswith("O")]
            if only:
                try:
                    want = ipaddress.ip_network(only, strict=False)
                    rows = [x for x in rows if x.prefix == want or (want.prefixlen == 128 and want.network_address in x.prefix)]
                except ValueError:
                    return INVALID
            out = [_v6_header(len(rib))]
            for x in rows:
                code = x.code.replace("O*IA", "OI").replace("O IA", "OI")
                pfx = f"{str(x.prefix.network_address).upper()}/{x.prefix.prefixlen}"
                if x.code in ("C", "L"):
                    out.append(f"{code:<3} {pfx} [{x.ad}/{x.metric}]\n     via {x.nexthops[0][1]}, {'directly connected' if x.code == 'C' else 'receive'}")
                else:
                    out.append(f"{code:<3} {pfx} [110/{x.metric}]")
                    for nh, ifn, _adv in x.nexthops:
                        out.append(f"     via {nh}, {ifn}")
            return "\n".join(out) + "\n"

        rows = [x for x in rib if not ospf_only or x.code.startswith("O")]
        default = next((x for x in rib if x.prefix.prefixlen == 0), None)
        out = [_ROUTE_CODES_V4]
        if default:
            out.append(f"Gateway of last resort is {default.nexthops[0][0]} to network 0.0.0.0\n")
        else:
            out.append("Gateway of last resort is not set\n")
        # group by classful major network, as IOS prints it
        groups: dict = {}
        for x in rib:
            if x.prefix.prefixlen == 0:
                continue
            major = ipaddress.ip_network(f"{x.prefix.network_address}/{classful_mask(str(x.prefix.network_address))}", strict=False)
            groups.setdefault(major, []).append(x)
        if default and default in rows:
            out += self._route_lines(r, default, "", indent=False)
        for major in sorted(groups):
            members = groups[major]
            shown = [x for x in members if x in rows]
            if not shown:
                continue
            masks = sorted({x.prefix.prefixlen for x in members})
            if len(masks) == 1 and masks[0] != major.prefixlen:
                out.append(f"      {major.network_address}/{masks[0]} is subnetted, {len(members)} subnets")
                for x in shown:
                    out += self._route_lines(r, x, str(x.prefix.network_address))
            elif len(masks) == 1:
                for x in shown:
                    out += self._route_lines(r, x, str(x.prefix), indent=False)
            else:
                out.append(f"      {major} is variably subnetted, {len(members)} subnets, {len(masks)} masks")
                for x in shown:
                    out += self._route_lines(r, x, str(x.prefix))
        return "\n".join(out) + "\n"

    def _route_lines(self, r: str, x: Route, label: str, indent: bool = True) -> list[str]:
        if not label:
            label = str(x.prefix)
        code = x.code
        pad = f"{code:<8}" if indent else f"{code:<6}"
        age = _hms(self.age(("rt", r, str(x.prefix), x.code)))
        if code == "C":
            return [f"{pad}{label} is directly connected, {x.nexthops[0][1]}"]
        if code == "L":
            return [f"{pad}{label} is directly connected, {x.nexthops[0][1]}"]
        if code == "S":
            nh, ifn, _ = x.nexthops[0]
            return [f"{pad}{label} is directly connected, {ifn}" if ifn else f"{pad}{label} [1/0] via {nh}"]
        lines = []
        for k, (nh, ifn, _adv) in enumerate(x.nexthops):
            if k == 0:
                lines.append(f"{pad}{label} [{x.ad}/{x.metric}] via {nh}, {age}, {ifn}")
            else:
                lines.append(" " * (len(pad) + len(label) + 1) + f"[{x.ad}/{x.metric}] via {nh}, {age}, {ifn}")
        return lines

    def route_lookup(self, r: str, addr: str) -> str:
        ip = ipaddress.ip_address(addr)
        cands = [x for x in self._rib(r, "v4") if ip in x.prefix]
        if not cands:
            return "% Network not in table\n"
        x = max(cands, key=lambda x: (x.prefix.prefixlen, -x.ad))
        if x.code in ("C", "L"):
            return (f"Routing entry for {x.prefix}\n  Known via \"connected\", distance 0, metric 0 (connected, via interface)\n"
                    f"  Routing Descriptor Blocks:\n  * directly connected, via {x.nexthops[0][1]}\n"
                    "      Route metric is 0, traffic share count is 1\n")
        if x.code == "S":
            return (f"Routing entry for {x.prefix}\n  Known via \"static\", distance 1, metric 0 (connected)\n"
                    f"  Routing Descriptor Blocks:\n  * directly connected, via {x.nexthops[0][1] or x.nexthops[0][0]}\n"
                    "      Route metric is 0, traffic share count is 1\n")
        age = _hms(self.age(("rt", r, str(x.prefix), x.code)))
        kind = {"O": "intra area", "O IA": "inter area", "O*IA": "inter area", "O E2": "extern 2, forward metric 20",
                "O E1": "extern 1", "O N2": "NSSA extern 2, forward metric 10", "O N1": "NSSA extern 1"}.get(x.code, x.kind)
        lines = [f"Routing entry for {x.prefix}",
                 f"  Known via \"ospf 1\", distance 110, metric {x.metric}, type {kind}",
                 f"  Last update from {x.nexthops[0][0]} on {x.nexthops[0][1]}, {age} ago",
                 "  Routing Descriptor Blocks:"]
        for k, (nh, ifn, adv) in enumerate(x.nexthops):
            lines.append(f"  {'*' if k == 0 else ' '} {nh}, from {adv}, {age} ago, via {ifn}")
            lines.append(f"      Route metric is {x.metric}, traffic share count is 1")
        return "\n".join(lines) + "\n"

    # -- BFD / IP SLA ------------------------------------------------------------------------------------------------
    def bfd(self, r: str) -> str:
        sess = self.s.bfd.get(r, [])
        if not sess:
            return ""
        out = ["\nIPv4 Sessions", "NeighAddr                              LD/RD         RH/RS     State     Int"]
        for b in sess:
            out.append(f"{b['neighbor']:<38} {str(b['ld']) + '/' + str(b['rd']):<13} {b['state']:<9} {b['state']:<9} {short_if(b['iface'])}")
        return "\n".join(out) + "\n"

    def sla(self, r: str) -> str:
        cfg = self.m.configs[r]
        if not cfg.sla:
            return "IPSLAs Latest Operation Statistics\n\n"
        out = ["IPSLAs Latest Operation Statistics", ""]
        for sid, op in sorted(cfg.sla.items()):
            target = op.get("target")
            ok = False
            hops = 1
            if target and sid in cfg.sla_scheduled:
                ip = ipaddress.ip_address(target)
                cands = [x for x in self._rib(r, "v4") if ip in x.prefix]
                ok = bool(cands)
                if cands:
                    best = max(cands, key=lambda x: x.prefix.prefixlen)
                    hops = 1 + best.metric // 10
            freq = max(1, op.get("frequency") or 60)
            runs = int((self.now - self.started) // freq) + 1
            rtt = 4 * hops + int(self.now // freq) % 5
            out += [f"IPSLA operation id: {sid}",
                    f"        Latest RTT: {rtt if ok else 'NoConnection/Busy/Timeout'}{' milliseconds' if ok else ''}",
                    "Latest operation start time: " + time.strftime("%H:%M:%S UTC %a %b %d %Y", time.gmtime(self.now - (self.now % freq))),
                    f"Latest operation return code: {'OK' if ok else 'Timeout'}",
                    f"Number of successes: {runs if ok else 0}",
                    f"Number of failures: {0 if ok else runs}",
                    "Operation time to live: Forever", ""]
        return "\n".join(out) + "\n"

    def version(self, r: str) -> str:
        up = int(self.now - self.started)
        upt = f"{up // 3600} hours, {(up // 60) % 60} minutes" if up >= 3600 else f"{(up // 60) % 60} minutes"
        cfg = self.m.configs[r]
        fe = sum(1 for n in cfg.ifaces if n.startswith("FastEthernet"))
        eth = sum(1 for n in cfg.ifaces if n.startswith("Ethernet"))
        return ("Cisco IOS Software, 7200 Software (C7200-ADVENTERPRISEK9-M), Version 15.2(4)S6, RELEASE SOFTWARE (fc1)\n"
                "Technical Support: http://www.cisco.com/techsupport\n"
                "Copyright (c) 1986-2014 by Cisco Systems, Inc.\n"
                "Compiled Fri 08-Aug-14 02:03 by prod_rel_team\n\n"
                "ROM: ROMMON Emulation Microcode\n"
                "BOOTLDR: 7200 Software (C7200-ADVENTERPRISEK9-M), Version 15.2(4)S6, RELEASE SOFTWARE (fc1)\n\n"
                f"{cfg.hostname} uptime is {upt}\n"
                'System image file is "disk0:c7200-adventerprisek9-mz.152-4.S6"\n'
                "Last reload reason: Unknown reason\n\n"
                "Cisco 7206VXR (NPE400) processor (revision A) with 245760K/16384K bytes of memory.\n"
                f"Processor board ID 42792{sorted(self.m.configs).index(r) + 1:05d}\n"
                "R7000 CPU at 150MHz, Implementation 39, Rev 2.1, 256KB L2 Cache\n"
                "6 slot VXR midplane, Version 2.1\n\n"
                "Last reset from power-on\n\n"
                "PCI bus mb0_mb1 (Slots 0, 1, 3 and 5) has a capacity of 600 bandwidth points.\n"
                "Current configuration on bus mb0_mb1 has a total of 400 bandwidth points. \n"
                "This configuration is within the PCI bus capacity and is supported. \n\n"
                f"{eth} Ethernet interfaces\n{fe} FastEthernet interface\n"
                "509K bytes of NVRAM.\n\n"
                "126976K bytes of ATA PCMCIA card at slot 0 (Sector size 512 bytes).\n"
                "8192K bytes of Flash internal SIMM (Sector size 256K).\n"
                "Configuration register is 0x2102\n")


def _v6_header(n: int) -> str:
    return f"IPv6 Routing Table - default - {n} entries\n{_ROUTE_CODES_V6}"


def classful_mask(addr: str) -> int:
    first = int(addr.split(".")[0])
    return 8 if first < 128 else 16 if first < 192 else 24


def _brief_order(i) -> tuple:
    """`show ip interface brief` order on IOS: physical ports by slot/port (Fa0/0, Et1/0 ...), then loopbacks."""
    return (i.name.startswith("Loopback"), [int(x) for x in re.findall(r"\d+", i.name)], i.name)
