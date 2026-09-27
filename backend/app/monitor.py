"""Polls every router for OSPF neighbor states, interface roles (DR/BDR), route counts
by type and IP SLA results. State changes go to Kafka as events (ospf.neighbor.events); a full
snapshot per poll (ospf.neighbor.snapshots) is turned into Prometheus gauges by the exporter."""
from __future__ import annotations

import asyncio
import logging
import re
import time

from . import bus
from . import devices as dev_mod
from .config import settings
from .inventory import Device, build_devices

log = logging.getLogger("ospf.monitor")

# 10.255.0.3   100   FULL/DR   00:00:33   10.0.123.3   Ethernet1/0      (role is "-" on point-to-point)
_NBR = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s+([A-Z0-9]+)/\s*(\S+)\s+(?:\d\d:\d\d:\d\d|-)\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s*$"
)
# Et1/0   1   0   10.0.123.1/24   10   DR   2/2
_IFACE = re.compile(r"^(\S+)\s+\d+\s+(\S+)\s+(\d{1,3}(?:\.\d{1,3}){3}/\d+)\s+(\d+)\s+(\S+)\s+(\d+)/(\d+)\s*$")
_ROUTE = re.compile(r"^(O(?: IA| E1| E2| N1| N2)?)\s", re.MULTILINE)
# 10.1.34.2   1/1   Up   Up   Et1/0
_BFD = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})\s+\d+/\d+\s+(?:\S+\s+)?(Up|Down|Init|AdminDown)\s+(\S+)\s*$", re.IGNORECASE)
_SLA_ID = re.compile(r"IPSLA operation id:\s*(\d+)")
_SLA_RTT = re.compile(r"Latest RTT:\s*(\d+)\s*milliseconds", re.IGNORECASE)
_SLA_RC = re.compile(r"Latest operation return code:\s*(\S+)")

# neighbor state -> number, so Grafana can draw a state timeline
STATE_CODE = {"DOWN": 0, "ATTEMPT": 1, "INIT": 2, "2WAY": 3, "EXSTART": 4, "EXCHANGE": 5, "LOADING": 6, "FULL": 7}

STATE: dict[tuple[str, str], dict] = {}        # (router, neighbor id) -> last neighbor
ROLE: dict[tuple[str, str], str] = {}          # (router, interface) -> last DR/BDR/DROTH state
REACHABLE: dict[str, bool] = {}
LAST: dict[str, dict] = {}                     # router -> last snapshot, served by /api/monitor/state


def parse_neighbors(output: str) -> list[dict]:
    out = []
    for line in output.splitlines():
        m = _NBR.match(line.strip())
        if not m:
            continue
        rid, pri, state, role, addr, iface = m.groups()
        out.append({"neighbor": rid, "priority": int(pri), "state": state, "state_code": STATE_CODE.get(state, 0),
                    "role": role, "address": addr, "interface": iface, "full": state == "FULL"})
    return out


# OSPFv3: the address column is replaced by the neighbor's Interface ID
# 10.255.0.1   1   FULL/DROTHER   00:00:34   3   Ethernet1/0
_NBR6 = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s+([A-Z0-9]+)/\s*(\S+)\s+(?:\d\d:\d\d:\d\d|-)\s+(\d+)\s+(\S+)\s*$"
)


def parse_neighbors_v6(output: str) -> list[dict]:
    out = []
    for line in output.splitlines():
        m = _NBR6.match(line.strip())
        if not m:
            continue
        rid, pri, state, role, intf_id, iface = m.groups()
        out.append({"neighbor": rid, "priority": int(pri), "state": state, "state_code": STATE_CODE.get(state, 0),
                    "role": role, "interface_id": int(intf_id), "interface": iface, "full": state == "FULL"})
    return out


def parse_interfaces(output: str) -> list[dict]:
    out = []
    for line in output.splitlines():
        m = _IFACE.match(line.strip())
        if not m:
            continue
        name, area, addr, cost, state, full, expected = m.groups()
        out.append({"interface": name, "area": area, "address": addr, "cost": int(cost),
                    "state": state, "neighbors": int(full), "expected": int(expected)})
    return out


def parse_routes(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in _ROUTE.finditer(output):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def parse_bfd(output: str) -> list[dict]:
    out = []
    for line in output.splitlines():
        m = _BFD.match(line.strip())
        if m:
            out.append({"neighbor": m.group(1), "state": m.group(2).capitalize(), "interface": m.group(3),
                        "up": m.group(2).lower() == "up"})
    return out


def parse_sla(output: str) -> list[dict]:
    out = []
    for block in re.split(r"(?=IPSLA operation id:)", output):
        i = _SLA_ID.search(block)
        if not i:
            continue
        rtt, rc = _SLA_RTT.search(block), _SLA_RC.search(block)
        out.append({"operation": int(i.group(1)), "rtt_ms": int(rtt.group(1)) if rtt else None,
                    "ok": bool(rc and rc.group(1) == "OK")})
    return out


def _poll_one(dev: Device) -> dict | None:
    try:
        cmds = ["show ip ospf neighbor", "show ip ospf interface brief", "show ip route ospf", "show ipv6 ospf neighbor"]
        cmds += ["show bfd neighbors"] if dev.bfd else []
        cmds += ["show ip sla statistics"] if dev.sla else []
        out = dict(zip(cmds, dev_mod.show_many(dev, cmds)))
        return {
            "neighbors": parse_neighbors(out["show ip ospf neighbor"]),
            "interfaces": parse_interfaces(out["show ip ospf interface brief"]),
            "routes": parse_routes(out["show ip route ospf"]),
            # OSPFv3 (scenarios 17-18): empty when the router runs no IPv6 OSPF. Shown in the UI; not turned into events/metrics.
            "neighbors_v6": parse_neighbors_v6(out["show ipv6 ospf neighbor"]),
            "sla": parse_sla(out["show ip sla statistics"]) if dev.sla else [],
            "bfd": parse_bfd(out["show bfd neighbors"]) if dev.bfd else [],
        }
    except Exception as exc:  # noqa: BLE001
        log.info("poll %s failed: %s", dev.name, exc)
        return None


def _process(dev: Device, snap: dict | None) -> None:
    reachable = snap is not None
    prev_reach = REACHABLE.get(dev.name)
    if prev_reach is not None and prev_reach != reachable:
        bus.emit(settings.topic_events, dev.name, {
            "type": "router_reachable" if reachable else "router_unreachable",
            "severity": "info" if reachable else "critical", "router": dev.name,
        })
    REACHABLE[dev.name] = reachable
    if snap is None:
        # keep the last known tables; only the reachability flag changes
        LAST[dev.name] = {**LAST.get(dev.name, {"router": dev.name, "role": dev.role, "neighbors": [], "neighbors_v6": [],
                                                 "interfaces": [], "routes": {}, "sla": [], "bfd": []}), "reachable": False}
        bus.emit(settings.topic_snapshots, dev.name, LAST[dev.name], ui=False)
        return

    seen = set()
    for n in snap["neighbors"]:
        k = (dev.name, n["neighbor"])
        seen.add(k)
        prev = STATE.get(k)
        if prev is not None and prev["state"] != n["state"]:
            bus.emit(settings.topic_events, dev.name, {
                "type": "neighbor_state_change",
                "severity": "info" if n["full"] else "warning",
                "router": dev.name, "neighbor": n["neighbor"], "interface": n["interface"],
                "state": n["state"], "prev_state": prev["state"],
            })
        STATE[k] = n
    for k in [k for k in STATE if k[0] == dev.name and k not in seen]:
        gone = STATE[k]                             # adjacency dropped out of the neighbor table entirely
        if gone["state"] != "DOWN":
            bus.emit(settings.topic_events, dev.name, {
                "type": "neighbor_lost", "severity": "critical", "router": dev.name,
                "neighbor": k[1], "interface": gone["interface"], "state": "DOWN", "prev_state": gone["state"],
            })
        # keep reporting it as DOWN so Grafana shows the outage and the not-Full alert can fire
        STATE[k] = {**gone, "state": "DOWN", "state_code": 0, "full": False, "role": "-"}
        snap["neighbors"].append(STATE[k])

    for i in snap["interfaces"]:
        k = (dev.name, i["interface"])
        prev = ROLE.get(k)
        if prev is not None and prev != i["state"]:
            bus.emit(settings.topic_events, dev.name, {
                "type": "interface_role_change", "severity": "info", "router": dev.name,
                "interface": i["interface"], "area": i["area"], "state": i["state"], "prev_state": prev,
            })
        ROLE[k] = i["state"]

    LAST[dev.name] = {"router": dev.name, "role": dev.role, "reachable": True, **snap}
    bus.emit(settings.topic_snapshots, dev.name, LAST[dev.name], ui=False)


def snapshot() -> list[dict]:
    return [LAST[r] for r in sorted(LAST)]


async def run_forever() -> None:
    while True:
        t0 = time.time()
        try:
            devs = list(build_devices().values())
            results = await asyncio.gather(*(asyncio.to_thread(_poll_one, d) for d in devs))
            for d, r in zip(devs, results):
                _process(d, r)
        except Exception:  # noqa: BLE001
            log.exception("monitor cycle failed")
        await asyncio.sleep(max(1.0, settings.poll_interval - (time.time() - t0)))
