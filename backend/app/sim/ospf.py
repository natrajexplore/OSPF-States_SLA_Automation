"""The OSPF model: from the routers' configuration and the lab's cabling, compute what IOS would show.

compute() is a pure function of (configs, links, DR memory, convergence memory, now) and returns a Snapshot with, per
address family (v4 = OSPFv2, v6 = OSPFv3): neighbor tables, interface states, the LSDB and the routing table.
"""
from __future__ import annotations

import heapq
import ipaddress
from dataclasses import dataclass, field

from .iosconfig import Iface, RouterConfig

INF = float("inf")
BW_KBPS = {"FastEthernet": 100_000, "GigabitEthernet": 1_000_000, "Ethernet": 10_000, "Loopback": 8_000_000, "Serial": 1544}


def _bw(name: str) -> int:
    return next((v for k, v in BW_KBPS.items() if name.startswith(k)), 10_000)


def classful_mask(addr: str) -> int:
    first = int(addr.split(".")[0])
    return 8 if first < 128 else 16 if first < 192 else 24


@dataclass
class Neighbor:
    rid: str
    router: str              # lab name of the neighbor
    priority: int
    state: str               # FULL, 2WAY, EXSTART, EXCHANGE, INIT, LOADING
    role: str                # DR, BDR, DROTHER, -
    address: str             # neighbor's address on the link (v4) / link-local (v6)
    iface: str               # local interface
    intf_id: int = 0         # neighbor's interface ID (OSPFv3)

    @property
    def full(self) -> bool:
        return self.state == "FULL"


@dataclass
class IfState:
    router: str
    iface: str
    area: int
    net_type: str            # BROADCAST, POINT_TO_POINT, LOOPBACK
    state: str               # DR, BDR, DROTHER, POINT_TO_POINT, LOOPBACK, WAITING
    cost: int
    priority: int
    hello_ms: int
    dead: int
    address: str             # 10.0.123.1/24, or the first IPv6 address
    dr: tuple[str, str] | None = None     # (rid, interface address)
    bdr: tuple[str, str] | None = None
    instance: int = 0
    bfd: bool = False


@dataclass
class Route:
    prefix: ipaddress._BaseNetwork
    code: str                # C, L, S, O, O IA, O*IA, O E2, O N2 (v6: O, OI)
    metric: int
    nexthops: list[tuple[str, str, str]]  # (next-hop address, interface, advertising router)
    ad: int = 110
    kind: str = ""           # intra area / inter area / external / nssa external (for `show ip route <addr>`)


@dataclass
class Lsa:
    ltype: str               # router, network, summary, asbr-summary, external, nssa
    lsid: str
    adv: str
    area: int | None
    mask: int = 32
    metric: int = 0
    mtype: int = 2
    extra: dict = field(default_factory=dict)


@dataclass
class AfView:
    neighbors: dict[str, list[Neighbor]] = field(default_factory=dict)      # router -> neighbors
    ifstates: dict[str, list[IfState]] = field(default_factory=dict)        # router -> participating interfaces
    routes: dict[str, list[Route]] = field(default_factory=dict)            # router -> RIB (connected + OSPF)
    lsdb: list[Lsa] = field(default_factory=list)
    abr: set[str] = field(default_factory=set)
    asbr: set[str] = field(default_factory=set)
    router_routes: dict[str, list[tuple]] = field(default_factory=dict)     # router -> [(rid, cost, nh, iface, kind, area, flags)]


@dataclass
class Snapshot:
    v4: AfView
    v6: AfView
    bfd: dict[str, list[dict]]


# --------------------------------------------------------------------------------------------------------------------
class Model:
    """Holds the lab's cabling and the state OSPF keeps between computations (DR/BDR, adjacency timers)."""

    def __init__(self, configs: dict[str, RouterConfig], links: list[dict], converge: float = 4.0) -> None:
        self.configs = configs
        self.order = list(configs)
        # links: [{name, members: [(router, ifname)]}]
        self.links = links
        self.converge = converge
        self.dr: dict[tuple[str, str], tuple[str | None, str | None]] = {}   # (af, link) -> (DR router, BDR router)
        self.adj_memo: dict[tuple, tuple[str, float]] = {}                  # (af, a, b, link) -> (final state, since)
        self.booted = False
        self.force_elect: set[tuple[str, str]] = set()

    # -- per interface parameters -----------------------------------------------------------------------------
    def rid(self, r: str, af: str) -> str | None:
        cfg = self.configs[r]
        proc = cfg.ospf if af == "v4" else cfg.ospf6
        if proc is None:
            return None
        if proc.router_id:
            return proc.router_id
        loops = [i.ip for i in cfg.ifaces.values() if i.loopback and i.ip and not i.shutdown]
        ups = [i.ip for i in cfg.ifaces.values() if i.ip and not i.shutdown]
        pool = loops or ups
        return max(pool, key=lambda a: ipaddress.ip_address(a)) if pool else None

    def participates(self, r: str, i: Iface, af: str) -> bool:
        cfg = self.configs[r]
        if i.shutdown:
            return False
        if af == "v4":
            return cfg.ospf is not None and i.ospf_area is not None and bool(i.ip) and self.rid(r, af) is not None
        return (cfg.ospf6 is not None and cfg.v6_routing and i.v6_area is not None and bool(i.v6_addrs)
                and self.rid(r, af) is not None)

    @staticmethod
    def area_of(i: Iface, af: str) -> int | None:
        return i.ospf_area if af == "v4" else i.v6_area

    @staticmethod
    def net_type(i: Iface, af: str) -> str:
        nt = i.net_type if af == "v4" else i.v6_net_type
        if i.loopback:
            return "POINT_TO_POINT" if nt == "point-to-point" else "LOOPBACK"
        return "POINT_TO_POINT" if nt == "point-to-point" else "BROADCAST"

    @staticmethod
    def timers(i: Iface, af: str) -> tuple[int, int]:
        """(hello in ms, dead in s)."""
        if af == "v4" and i.dead_minimal_mult:
            return 1000 // i.dead_minimal_mult, 1
        hello = (i.hello or 10) if af == "v4" else 10
        dead = (i.dead if af == "v4" and i.dead else 4 * hello)
        return hello * 1000, dead

    def cost(self, r: str, i: Iface, af: str) -> int:
        if af == "v4" and i.cost:
            return i.cost
        proc = self.configs[r].ospf if af == "v4" else self.configs[r].ospf6
        ref = proc.ref_bw if proc else 100
        return max(1, (ref * 1000) // _bw(i.name))

    def area_kind(self, r: str, area: int, af: str):
        proc = self.configs[r].ospf if af == "v4" else self.configs[r].ospf6
        return proc.area(area) if proc else None

    def addr(self, r: str, i: Iface, af: str) -> str:
        if af == "v4":
            return i.ip or "0.0.0.0"
        return self.link_local(r, i)

    def link_local(self, r: str, i: Iface) -> str:
        n = self.order.index(r) + 1
        return f"FE80::C8{n:02X}:FF:FE00:{self.intf_id(i.name):X}"

    @staticmethod
    def intf_id(name: str) -> int:
        digits = [int(x) for x in name.split("/") if x.isdigit()] if "/" in name else []
        if name.startswith("Loopback"):
            return 20 + int(name[8:] or 0)
        if digits:
            slot = int("".join(ch for ch in name.split("/")[0] if ch.isdigit()) or 0)
            return 2 + slot + digits[-1]
        return 1

    # -- events -----------------------------------------------------------------------------------------------
    def clear_process(self, r: str) -> None:
        """`clear ip ospf process`: the router's adjacencies restart; on a segment where it was DR or BDR a new
        election follows (all three routers of the LAN are cleared within seconds, so the wait timers overlap)."""
        for key in [k for k in self.adj_memo if k[0] == "v4" and r in (k[1], k[2])]:
            del self.adj_memo[key]
        for link in self.links:
            if any(m[0] == r for m in link["members"]):
                dr, bdr = self.dr.get(("v4", link["name"]), (None, None))
                if r in (dr, bdr):
                    self.force_elect.add(("v4", link["name"]))

    # -- computation ------------------------------------------------------------------------------------------
    def compute(self, now: float) -> Snapshot:
        v4 = self._af("v4", now)
        v6 = self._af("v6", now)
        self.booted = True
        return Snapshot(v4=v4, v6=v6, bfd=self._bfd(v4))

    def _members(self, link: dict, af: str) -> list[tuple[str, Iface]]:
        out = []
        for r, ifn in link["members"]:
            i = self.configs[r].ifaces.get(ifn)
            if i is not None and self.participates(r, i, af):
                out.append((r, i))
        return out

    def _compat(self, a: tuple[str, Iface], b: tuple[str, Iface], af: str) -> str | None:
        """None = hellos rejected (no neighbor), 'ok', 'nettype' or 'mtu' (stuck before Full)."""
        (ra, ia), (rb, ib) = a, b
        if self.area_of(ia, af) != self.area_of(ib, af):
            return None
        if self.timers(ia, af) != self.timers(ib, af):
            return None
        ka, kb = self.area_kind(ra, ia.ospf_area if af == "v4" else ia.v6_area, af), \
            self.area_kind(rb, ib.ospf_area if af == "v4" else ib.v6_area, af)
        if (ka.kind if ka else "normal") != (kb.kind if kb else "normal"):
            return None
        if af == "v6" and ia.v6_instance != ib.v6_instance:
            return None
        if af == "v4" and ia.ip and ib.ip and ia.mask and ib.mask:
            na = ipaddress.ip_interface(f"{ia.ip}/{ia.mask}").network
            nb = ipaddress.ip_interface(f"{ib.ip}/{ib.mask}").network
            if na != nb:
                return None
        if self.net_type(ia, af) != self.net_type(ib, af):
            return "nettype"
        if ia.mtu != ib.mtu:
            return "mtu"
        return "ok"

    def _elect(self, af: str, link: dict, cands: list[tuple[str, Iface]]) -> tuple[str | None, str | None]:
        def prio(r: str, i: Iface) -> int:
            return i.priority if af == "v4" else i.v6_priority

        eligible = [(r, i) for r, i in cands if prio(r, i) > 0]
        names = {r for r, _ in eligible}
        key = (af, link["name"])
        dr, bdr = self.dr.get(key, (None, None))
        ranked = sorted(eligible, key=lambda x: (prio(*x), ipaddress.ip_address(self.rid(x[0], af))), reverse=True)
        if key in self.force_elect or (dr is None and bdr is None):
            self.force_elect.discard(key)
            dr = ranked[0][0] if ranked else None
            bdr = ranked[1][0] if len(ranked) > 1 else None
        else:
            if dr not in names:                       # DR gone (or priority 0): the BDR takes over
                dr, bdr = (bdr if bdr in names else None), None
                if dr is None and ranked:
                    dr = ranked[0][0]
            if bdr not in names or bdr == dr:
                rest = [r for r, _ in ranked if r != dr]
                bdr = rest[0] if rest else None
        self.dr[key] = (dr, bdr)
        return dr, bdr

    def _progress(self, key: tuple, final: str, now: float) -> str:
        prev = self.adj_memo.get(key)
        if prev is None:
            since = now if self.booted else -INF
        elif prev[0] != final:
            since = now
        else:
            since = prev[1]
        self.adj_memo[key] = (final, since)
        if final not in ("FULL", "2WAY") or now - since >= self.converge:
            return final
        frac = (now - since) / self.converge
        if final == "2WAY":
            return "INIT" if frac < 0.5 else "2WAY"
        return "INIT" if frac < 0.3 else "EXSTART" if frac < 0.55 else "EXCHANGE" if frac < 0.8 else "LOADING"

    def _af(self, af: str, now: float) -> AfView:
        view = AfView()
        rid = {r: self.rid(r, af) for r in self.configs}
        for r in self.configs:
            view.neighbors[r] = []
            view.ifstates[r] = []
        seg_dr: dict[str, tuple[str | None, str | None]] = {}
        # (router, ifname) -> list of (neighbor router, state)
        adj: dict[tuple[str, str], list[tuple[str, str]]] = {}
        seen: set[tuple] = set()

        # 1. neighbors per link
        for link in self.links:
            mem = self._members(link, af)
            bcast = [m for m in mem if self.net_type(m[1], af) == "BROADCAST"]
            # who hears whom
            hears = {(a[0], b[0]): self._compat(a, b, af) for a in mem for b in mem if a[0] != b[0]}
            if bcast:
                cands = [m for m in bcast if any(hears.get((m[0], o[0])) for o in mem if o[0] != m[0])] or bcast
                seg_dr[link["name"]] = self._elect(af, link, cands)
            dr, bdr = seg_dr.get(link["name"], (None, None))
            for a in mem:
                for b in mem:
                    if a[0] == b[0]:
                        continue
                    c = hears[(a[0], b[0])]
                    if c is None:
                        continue
                    a_nt, b_nt = self.net_type(a[1], af), self.net_type(b[1], af)
                    role = "-"
                    if c == "nettype":
                        final = "EXSTART" if a_nt == "POINT_TO_POINT" else "2WAY"
                        role = "-" if a_nt == "POINT_TO_POINT" else "DROTHER"
                    elif c == "mtu":
                        final = "EXCHANGE" if a[1].mtu > b[1].mtu else "EXSTART"
                    elif a_nt == "BROADCAST":
                        role = "DR" if b[0] == dr else "BDR" if b[0] == bdr else "DROTHER"
                        a_role = "DR" if a[0] == dr else "BDR" if a[0] == bdr else "DROTHER"
                        final = "2WAY" if role == "DROTHER" and a_role == "DROTHER" else "FULL"
                    else:
                        final = "FULL"
                    seen.add((af, a[0], b[0], link["name"]))
                    state = self._progress((af, a[0], b[0], link["name"]), final, now)
                    prio = 0 if a_nt == "POINT_TO_POINT" else (b[1].priority if af == "v4" else b[1].v6_priority)
                    view.neighbors[a[0]].append(Neighbor(
                        rid=rid[b[0]], router=b[0], priority=prio, state=state, role=role,
                        address=self.addr(b[0], b[1], af), iface=a[1].name, intf_id=self.intf_id(b[1].name)))
                    adj.setdefault((a[0], a[1].name), []).append((b[0], state))

        # a neighbor that vanished (hellos rejected) starts from scratch when it comes back
        for key in [k for k in self.adj_memo if k[0] == af and k not in seen]:
            del self.adj_memo[key]

        # 2. interface states
        link_of = {(r, ifn): link for link in self.links for r, ifn in link["members"]}
        for r, cfg in self.configs.items():
            for i in cfg.ifaces.values():
                if not self.participates(r, i, af):
                    continue
                nt = self.net_type(i, af)
                hello, dead = self.timers(i, af)
                link = link_of.get((r, i.name))
                dr = bdr = None
                if nt == "LOOPBACK":
                    st = "LOOPBACK"
                elif nt == "POINT_TO_POINT":
                    st = "POINT_TO_POINT"
                else:
                    d, b = seg_dr.get(link["name"], (None, None)) if link else (r, None)
                    if link is None:
                        d = r
                    st = "DR" if d == r else "BDR" if b == r else "DROTHER" if d else "WAITING"
                    members = {m[0]: m[1] for m in (self._members(link, af) if link else [(r, i)])}
                    if d in members:
                        dr = (rid[d], self.addr(d, members[d], af) if af == "v4" else rid[d])
                    if b in members:
                        bdr = (rid[b], self.addr(b, members[b], af) if af == "v4" else rid[b])
                if af == "v4":
                    address = f"{i.ip}/{ipaddress.ip_network(f'0.0.0.0/{i.mask}').prefixlen}"
                else:
                    address = i.v6_addrs[0].upper()
                view.ifstates[r].append(IfState(
                    router=r, iface=i.name, area=self.area_of(i, af), net_type=nt, state=st, cost=self.cost(r, i, af),
                    priority=i.priority if af == "v4" else i.v6_priority, hello_ms=hello, dead=dead, address=address,
                    dr=dr, bdr=bdr, instance=i.v6_instance if af == "v6" else 0,
                    bfd=bool(af == "v4" and i.ospf_bfd)))

        # 3. topology per area: nodes "R:<router>" and "N:<link>" (transit broadcast segments)
        def full_with(r: str, ifn: str, other: str) -> bool:
            return any(n == other and s == "FULL" for n, s in adj.get((r, ifn), []))

        areas: dict[int, dict] = {}            # area -> {"edges": {node: [(node, cost, hop)]}, "prefixes": [(net, owner, cost)]}

        def area_rec(a: int) -> dict:
            return areas.setdefault(a, {"edges": {}, "prefixes": [], "routers": set()})

        for r, cfg in self.configs.items():
            for i in cfg.ifaces.values():
                if not self.participates(r, i, af):
                    continue
                a = self.area_of(i, af)
                rec = area_rec(a)
                rec["routers"].add(r)
                nt = self.net_type(i, af)
                c = self.cost(r, i, af)
                nets = self._nets(i, af)
                link = link_of.get((r, i.name))
                if nt == "LOOPBACK":                     # a loopback is a /32 (/128) host route unless it is point-to-point
                    hosts = ([ipaddress.ip_network(f"{i.ip}/32")] if af == "v4" else
                             [ipaddress.ip_network(f"{ipaddress.ip_interface(a).ip}/128") for a in i.v6_addrs])
                    for host in hosts:
                        rec["prefixes"].append((host, f"R:{r}", c))
                    continue
                if nt == "POINT_TO_POINT":
                    for other, state in adj.get((r, i.name), []):
                        if state == "FULL" and link and full_with(other, self._peer_if(link, other), r):
                            oi = self.configs[other].ifaces[self._peer_if(link, other)]
                            rec["edges"].setdefault(f"R:{r}", []).append((f"R:{other}", c, (self.addr(other, oi, af), i.name)))
                    for net in nets:
                        rec["prefixes"].append((net, f"R:{r}", c))
                    continue
                # broadcast
                d, _b = seg_dr.get(link["name"], (None, None)) if link else (None, None)
                transit = bool(link and d and (
                    (d == r and any(s == "FULL" for _, s in adj.get((r, i.name), []))) or full_with(r, i.name, d)))
                if transit:
                    n = f"N:{link['name']}"
                    rec["edges"].setdefault(f"R:{r}", []).append((n, c, ("direct", i.name)))
                    rec["edges"].setdefault(n, []).append((f"R:{r}", 0, (self.addr(r, i, af), None)))
                    for net in nets:
                        if (net, n, 0) not in rec["prefixes"]:
                            rec["prefixes"].append((net, n, 0))
                else:
                    for net in nets:
                        rec["prefixes"].append((net, f"R:{r}", c))

        # 4. ABRs, summaries, externals
        part_areas: dict[str, set[int]] = {r: set() for r in self.configs}
        for a, rec in areas.items():
            for r in rec["routers"]:
                part_areas[r].add(a)
        abrs = {r for r, s in part_areas.items() if 0 in s and len(s) > 1}
        view.abr = abrs

        spf: dict[tuple[str, int], tuple[dict, dict]] = {}
        for a, rec in areas.items():
            for r in rec["routers"]:
                spf[(r, a)] = self._dijkstra(rec["edges"], f"R:{r}")

        connected = {r: self._connected(r, af) for r in self.configs}

        def intra(r: str) -> dict:
            """prefix -> (cost, nexthops, area) for r's intra-area routes (not connected)."""
            out: dict = {}
            for a in part_areas[r]:
                dist, nh = spf[(r, a)]
                for net, owner, c in areas[a]["prefixes"]:
                    if net in connected[r] or owner == f"R:{r}" or owner not in dist:
                        continue
                    tot = dist[owner] + c
                    hops = [(addr, ifn, owner[2:] if owner.startswith("R:") else "") for addr, ifn in nh[owner]]
                    cur = out.get(net)
                    if cur is None or tot < cur[0]:
                        out[net] = (tot, hops, a)
                    elif tot == cur[0] and cur[2] == a:
                        out[net] = (tot, cur[1] + [h for h in hops if h not in cur[1]], a)
            return out

        intra_r = {r: intra(r) for r in self.configs}

        # summaries originated by each ABR into each attached area
        lsdb: list[Lsa] = []
        for x in sorted(abrs):
            for a in sorted(part_areas[x]):
                kind = self.area_kind(x, a, af)
                if kind and kind.kind == "stub":
                    lsdb.append(Lsa("summary", "0.0.0.0" if af == "v4" else "::", rid[x], a, mask=0, metric=1))
                if kind and kind.no_summary and kind.kind in ("stub", "nssa"):
                    continue
                for b in part_areas[x]:
                    if b == a:
                        continue
                    srcs = {net: c for net, (c, _h, ar) in intra_r[x].items() if ar == b}
                    for net, owner, c in areas[b]["prefixes"]:
                        if owner == f"R:{x}" or (owner.startswith("N:") and net in connected[x]):
                            srcs[net] = min(srcs.get(net, INF), c if owner == f"R:{x}" else self._own_cost(x, net, af))
                    for net, c in srcs.items():
                        if any(net == p for p, _o, _c in areas[a]["prefixes"]):
                            continue
                        lsdb.append(Lsa("summary", str(net.network_address), rid[x], a, mask=net.prefixlen, metric=int(c)))

        # externals (OSPFv2 only)
        ext7: list[Lsa] = []
        ext5: list[Lsa] = []
        if af == "v4":
            for r, cfg in self.configs.items():
                if cfg.ospf is None or not part_areas[r]:
                    continue
                for net, metric, mtype in self._redistributed(r):
                    view.asbr.add(r)
                    kinds = {a: (self.area_kind(r, a, af).kind) for a in part_areas[r]}
                    if r not in abrs and all(k == "nssa" for k in kinds.values()):
                        for a in kinds:
                            ext7.append(Lsa("nssa", str(net.network_address), rid[r], a, mask=net.prefixlen,
                                            metric=metric, mtype=mtype, extra={"asbr": r}))
                    elif any(k == "normal" for k in kinds.values()):
                        ext5.append(Lsa("external", str(net.network_address), rid[r], None, mask=net.prefixlen,
                                        metric=metric, mtype=mtype, extra={"asbr": r}))
            # NSSA translation by the NSSA ABR(s): `translate type7 always` wins, else the highest router ID
            for a in {lsa.area for lsa in ext7}:
                nssa_abrs = [x for x in abrs if a in part_areas[x] and self.area_kind(x, a, af).kind == "nssa"
                             and f"R:{x}" in areas[a]["edges"]]
                always = [x for x in nssa_abrs if self.area_kind(x, a, af).translate_always]
                trans = always or sorted(nssa_abrs, key=lambda x: ipaddress.ip_address(rid[x]))[-1:]
                for x in trans:
                    for lsa in ext7:
                        if lsa.area != a:
                            continue
                        dist, _ = spf[(x, a)]
                        if f"R:{lsa.extra['asbr']}" not in dist and lsa.extra["asbr"] != x:
                            continue
                        ext5.append(Lsa("external", lsa.lsid, rid[x], None, mask=lsa.mask, metric=lsa.metric,
                                        mtype=lsa.mtype, extra={"asbr": x, "translated": True}))
                    view.asbr.add(x)
        lsdb += ext7 + ext5

        # router LSAs / network LSAs (for `show ip ospf database`)
        for a, rec in areas.items():
            for r in sorted(rec["routers"]):
                links_n = sum(1 for p in rec["prefixes"] if p[1] == f"R:{r}") + len(rec["edges"].get(f"R:{r}", []))
                lsdb.append(Lsa("router", rid[r], rid[r], a, extra={"links": links_n}))
            for link in self.links:
                d, _b = seg_dr.get(link["name"], (None, None))
                if d and f"N:{link['name']}" in rec["edges"] and d in rec["routers"]:
                    di = self.configs[d].ifaces[self._peer_if(link, d)]
                    if self.area_of(di, af) == a:
                        lsdb.append(Lsa("network", self.addr(d, di, af) if af == "v4" else rid[d], rid[d], a,
                                        mask=ipaddress.ip_network(f"0.0.0.0/{di.mask}").prefixlen if af == "v4" else 0))
        view.lsdb = lsdb

        # 5. routing tables
        for r in self.configs:
            rib: dict = {}
            for net, (c, hops, _a) in intra_r[r].items():
                rib[net] = Route(net, "O", int(c), hops, kind="intra area")
            # inter-area: an ABR only uses summaries from the backbone
            use_areas = {0} & part_areas[r] if r in abrs else part_areas[r]
            for a in use_areas:
                dist, nh = spf[(r, a)]
                for lsa in lsdb:
                    if lsa.ltype != "summary" or lsa.area != a or lsa.adv == rid[r]:
                        continue
                    x = next((k for k, v in rid.items() if v == lsa.adv), None)
                    if x is None or f"R:{x}" not in dist:
                        continue
                    net = ipaddress.ip_network(f"{lsa.lsid}/{lsa.mask}")
                    if net in connected[r] or (net in rib and rib[net].code == "O"):
                        continue
                    tot = dist[f"R:{x}"] + lsa.metric
                    hops = [(addr, ifn, lsa.adv) for addr, ifn in nh[f"R:{x}"]]
                    code = ("O*IA" if lsa.mask == 0 else "O IA") if af == "v4" else "OI"
                    cur = rib.get(net)
                    if cur is None or tot < cur.metric:
                        rib[net] = Route(net, code, int(tot), hops, kind="inter area")
                    elif tot == cur.metric and cur.code == code:
                        cur.nexthops += [h for h in hops if h not in cur.nexthops]
            # route to each ASBR / translator (for externals and `show ip ospf border-routers`)
            rr = self._router_routes(r, rid, part_areas, abrs, spf, lsdb, view.asbr)
            view.router_routes[r] = rr
            if af == "v4":
                n2: dict = {}
                for lsa in ext7:
                    if lsa.area not in part_areas[r] or lsa.extra["asbr"] == r:
                        continue
                    dist, nh = spf[(r, lsa.area)]
                    asbr = f"R:{lsa.extra['asbr']}"
                    if asbr not in dist:
                        continue
                    net = ipaddress.ip_network(f"{lsa.lsid}/{lsa.mask}")
                    n2[net] = Route(net, f"O N{lsa.mtype}", lsa.metric, [(a_, i_, lsa.adv) for a_, i_ in nh[asbr]],
                                    kind="nssa external")
                sees5 = any(self.area_kind(r, a, af).kind == "normal" for a in part_areas[r])
                e5: dict = {}
                for lsa in ext5 if sees5 else []:
                    if lsa.extra["asbr"] == r:
                        continue
                    path = next((p for p in rr if p[0] == lsa.adv), None)
                    if path is None:
                        continue
                    net = ipaddress.ip_network(f"{lsa.lsid}/{lsa.mask}")
                    fwd = path[1]
                    cur = e5.get(net)
                    hops = [(h[0], h[1], lsa.adv) for h in path[2]]
                    if cur is None or (lsa.metric, fwd) < (cur[0].metric, cur[1]):
                        e5[net] = (Route(net, f"O E{lsa.mtype}", lsa.metric, hops, kind="external"), fwd)
                for net, rt in n2.items():
                    if net not in rib and net not in connected[r]:
                        rib[net] = rt
                for net, (rt, _f) in e5.items():
                    if net not in rib and net not in connected[r]:
                        rib[net] = rt
            view.routes[r] = list(connected[r].values()) + sorted(rib.values(), key=lambda x: (x.prefix.version, x.prefix))
        return view

    # -- helpers ----------------------------------------------------------------------------------------------
    @staticmethod
    def _peer_if(link: dict, router: str) -> str:
        return next(ifn for r, ifn in link["members"] if r == router)

    def _nets(self, i: Iface, af: str) -> list:
        if af == "v4":
            return [ipaddress.ip_interface(f"{i.ip}/{i.mask}").network] if i.ip and i.mask else []
        return [ipaddress.ip_interface(a).network for a in i.v6_addrs]

    def _own_cost(self, r: str, net, af: str) -> int:
        for i in self.configs[r].ifaces.values():
            if self.participates(r, i, af) and net in self._nets(i, af):
                return self.cost(r, i, af)
        return 1

    def _connected(self, r: str, af: str) -> dict:
        """The global-table connected (C) and local (L) routes, plus static routes (S) for v4."""
        out: dict = {}
        cfg = self.configs[r]
        for i in cfg.ifaces.values():
            if i.shutdown or i.vrf:
                continue
            if af == "v4" and i.ip and i.mask:
                net = ipaddress.ip_interface(f"{i.ip}/{i.mask}").network
                out[net] = Route(net, "C", 0, [("", i.name, "")], ad=0, kind="connected")
                if net.prefixlen < 32:
                    host = ipaddress.ip_network(f"{i.ip}/32")
                    out[host] = Route(host, "L", 0, [("", i.name, "")], ad=0, kind="local")
            elif af == "v6" and cfg.v6_routing:
                for a in i.v6_addrs:
                    itf = ipaddress.ip_interface(a)
                    out[itf.network] = Route(itf.network, "C", 0, [("", i.name, "")], ad=0, kind="connected")
                    host = ipaddress.ip_network(f"{itf.ip}/128")
                    out[host] = Route(host, "L", 0, [("", i.name, "")], ad=0, kind="local")
        if af == "v4":
            for prefix, mask, nh, vrf in cfg.statics:
                if vrf:
                    continue
                net = ipaddress.ip_network(f"{prefix}/{mask}", strict=False)
                if net not in out:
                    out[net] = Route(net, "S", 0, [(nh if nh[0].isdigit() else "", nh if not nh[0].isdigit() else "", "")],
                                     ad=1, kind="static")
        return out

    def _redistributed(self, r: str) -> list[tuple]:
        cfg = self.configs[r]
        out = []
        red = cfg.ospf.redistribute if cfg.ospf else {}
        if "static" in red:
            opt = red["static"]
            for prefix, mask, _nh, vrf in cfg.statics:
                if vrf:
                    continue
                net = ipaddress.ip_network(f"{prefix}/{mask}", strict=False)
                if opt["subnets"] or net.prefixlen == classful_mask(prefix):
                    out.append((net, opt["metric"], opt["mtype"]))
        if "connected" in red:
            opt = red["connected"]
            rmap = cfg.route_maps.get(opt["route_map"]) if opt["route_map"] else None
            for i in cfg.ifaces.values():
                if i.shutdown or i.vrf or not i.ip or not i.mask or self.participates(r, i, "v4"):
                    continue
                if opt["route_map"]:
                    if not rmap:
                        continue
                    hit = next((e for e in sorted(rmap, key=lambda e: e["seq"])
                                if not e["match_ifaces"] or i.name in e["match_ifaces"]), None)
                    if hit is None or hit["action"] != "permit":
                        continue
                net = ipaddress.ip_interface(f"{i.ip}/{i.mask}").network
                if opt["subnets"] or net.prefixlen == classful_mask(i.ip):
                    out.append((net, opt["metric"], opt["mtype"]))
        return out

    def _router_routes(self, r, rid, part_areas, abrs, spf, lsdb, asbrs) -> list[tuple]:
        """[(rid, cost, [(nh, iface)], kind 'i'/'I', area, flags)] - routes to ABRs and ASBRs."""
        out: dict[str, tuple] = {}
        for a in sorted(part_areas[r]):
            dist, nh = spf[(r, a)]
            for node, d in dist.items():
                if not node.startswith("R:") or node == f"R:{r}":
                    continue
                x = node[2:]
                flags = [f for f, cond in (("ABR", x in abrs), ("ASBR", x in asbrs)) if cond]
                if not flags:
                    continue
                cur = out.get(rid[x])
                if cur is None or d < cur[1]:
                    out[rid[x]] = (rid[x], d, list(nh[node]), "i", a, "/".join(flags))
        # ASBRs in other areas: through an ABR (type-4)
        for x in asbrs:
            if rid[x] in out or x == r:
                continue
            best = None
            for y in abrs:
                if y == r:
                    continue
                for a in part_areas[r] & part_areas[y]:
                    dist, nh = spf[(r, a)]
                    if f"R:{y}" not in dist:
                        continue
                    for b in part_areas[y]:
                        dy, _ = spf[(y, b)]
                        if f"R:{x}" in dy:
                            tot = dist[f"R:{y}"] + dy[f"R:{x}"]
                            if best is None or tot < best[1]:
                                best = (rid[x], tot, list(nh[f"R:{y}"]), "I", a, "ASBR")
                            elif tot == best[1]:
                                best[2].extend(h for h in nh[f"R:{y}"] if h not in best[2])
            if best:
                out[rid[x]] = best
        return sorted(out.values(), key=lambda t: ipaddress.ip_address(t[0]))

    @staticmethod
    def _dijkstra(edges: dict, root: str) -> tuple[dict, dict]:
        dist = {root: 0}
        nh: dict[str, list[tuple[str, str]]] = {root: []}
        pq = [(0, root)]
        done = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in done:
                continue
            done.add(u)
            for v, c, hop in edges.get(u, []):
                nd = d + c
                if u == root:
                    new = [hop] if hop[0] != "direct" else [("direct", hop[1])]
                elif nh[u] and nh[u][0][0] == "direct":
                    new = [(hop[0], ifn) for _, ifn in nh[u]]
                else:
                    new = list(nh[u])
                if nd < dist.get(v, INF):
                    dist[v], nh[v] = nd, new
                    heapq.heappush(pq, (nd, v))
                elif nd == dist.get(v) and v not in done:
                    nh[v] = nh[v] + [h for h in new if h not in nh[v]]
        return dist, nh

    def _bfd(self, v4: AfView) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {r: [] for r in self.configs}
        for r, nbrs in v4.neighbors.items():
            for n in nbrs:
                i = self.configs[r].ifaces[n.iface]
                peer_link = next((ln for ln in self.links if (r, n.iface) in [tuple(m) for m in ln["members"]]), None)
                if not peer_link or not (i.ospf_bfd and i.bfd):
                    continue
                pi = self.configs[n.router].ifaces[self._peer_if(peer_link, n.router)]
                if not (pi.ospf_bfd and pi.bfd):
                    continue
                out[r].append({"neighbor": n.address, "iface": n.iface, "state": "Up" if n.full else "Down",
                               "ld": self.intf_id(i.name) - 2, "rd": self.intf_id(pi.name) - 2,
                               "interval": i.bfd[0], "multiplier": i.bfd[2]})
        return out
