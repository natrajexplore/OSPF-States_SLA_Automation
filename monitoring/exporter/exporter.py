"""Kafka -> Prometheus bridge. Consumes the three OSPF topics and exposes /metrics."""
import json
import logging
import os
import time
from datetime import datetime

from confluent_kafka import Consumer
from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exporter")

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
T_EVENTS = os.getenv("TOPIC_EVENTS", "ospf.neighbor.events")
T_SNAP = os.getenv("TOPIC_SNAPSHOTS", "ospf.neighbor.snapshots")
T_CONFIG = os.getenv("TOPIC_CONFIG", "ospf.config.changes")

NBR = ["router", "neighbor", "interface"]
# 0 Down, 1 Attempt, 2 Init, 3 2-Way, 4 ExStart, 5 Exchange, 6 Loading, 7 Full
nbr_state = Gauge("ospf_neighbor_state", "OSPF neighbor state code (7 = Full)", NBR)
nbr_full = Gauge("ospf_neighbor_full", "1 if the adjacency is Full", NBR)
if_role = Gauge("ospf_interface_role", "1 for the current interface state (DR/BDR/DROTH/P2P/LOOP/...)",
                ["router", "interface", "area", "state"])
if_cost = Gauge("ospf_interface_cost", "OSPF interface cost", ["router", "interface", "area"])
if_nbrs = Gauge("ospf_interface_full_neighbors", "Full neighbors on the interface", ["router", "interface"])
routes = Gauge("ospf_routes", "OSPF routes in the RIB by type (O, O IA, O E1, O E2, O N1, O N2)", ["router", "type"])
bfd_up = Gauge("ospf_bfd_up", "1 if the BFD session is Up", NBR)
sla_rtt = Gauge("ospf_sla_rtt_milliseconds", "IP SLA latest RTT", ["router", "operation"])
sla_up = Gauge("ospf_sla_up", "1 if the IP SLA latest return code is OK", ["router", "operation"])
router_reach = Gauge("ospf_router_reachable", "1 if router answered the last poll", ["router"])
snap_seen = Gauge("ospf_snapshot_timestamp_seconds", "Time of last snapshot per router", ["router"])
transitions = Counter("ospf_neighbor_transitions_total", "Neighbor state changes", ["router", "neighbor", "to_state"])
lost = Counter("ospf_neighbor_lost_total", "Neighbors that vanished from the table", ["router", "neighbor"])
dr_changes = Counter("ospf_interface_role_changes_total", "Interface role changes (DR/BDR/DROTH)",
                     ["router", "interface", "to_state"])
config_changes = Counter("ospf_config_changes_total", "Config pushes from the backend",
                         ["scenario", "concept", "mode", "result"])
config_last = Gauge("ospf_config_last_change_timestamp_seconds", "Time of last config push",
                    ["scenario", "concept", "mode"])
config_dur = Gauge("ospf_config_last_duration_seconds", "Duration of last config push", ["scenario"])
consumed = Counter("ospf_exporter_messages_total", "Kafka messages consumed", ["topic"])

_series: dict[tuple, set] = {}


def ts(v):
    try:
        return datetime.fromisoformat(v).timestamp()
    except Exception:  # noqa: BLE001
        return time.time()


def _set(router: str, gauge: Gauge, items: dict[tuple, float]) -> None:
    """Set every series for `router`, and drop those that vanished (e.g. an interface changed role)."""
    key = (gauge._name, router)  # noqa: SLF001
    for old in _series.get(key, set()) - set(items):
        try:
            gauge.remove(*old)
        except KeyError:
            pass
    for labels, value in items.items():
        gauge.labels(*labels).set(value)
    _series[key] = set(items)


def on_snapshot(m):
    r = m["router"]
    router_reach.labels(r).set(1 if m["reachable"] else 0)
    snap_seen.labels(r).set(ts(m["ts"]))
    if not m["reachable"]:
        return                                     # keep last known tables, only flag reachability
    _set(r, nbr_state, {(r, n["neighbor"], n["interface"]): n["state_code"] for n in m["neighbors"]})
    _set(r, nbr_full, {(r, n["neighbor"], n["interface"]): int(n["full"]) for n in m["neighbors"]})
    _set(r, if_role, {(r, i["interface"], i["area"], i["state"]): 1 for i in m["interfaces"]})
    _set(r, if_cost, {(r, i["interface"], i["area"]): i["cost"] for i in m["interfaces"]})
    _set(r, if_nbrs, {(r, i["interface"]): i["neighbors"] for i in m["interfaces"]})
    _set(r, routes, {(r, t): c for t, c in m["routes"].items()})
    _set(r, bfd_up, {(r, b["neighbor"], b["interface"]): int(b["up"]) for b in m.get("bfd", [])})
    sla = m.get("sla", [])
    _set(r, sla_up, {(r, str(s["operation"])): int(s["ok"]) for s in sla})
    _set(r, sla_rtt, {(r, str(s["operation"])): s["rtt_ms"] for s in sla if s["rtt_ms"] is not None})


def on_event(m):
    t = m["type"]
    if t == "neighbor_state_change":
        transitions.labels(m["router"], m["neighbor"], m["state"]).inc()
    elif t == "neighbor_lost":
        lost.labels(m["router"], m["neighbor"]).inc()
        transitions.labels(m["router"], m["neighbor"], "DOWN").inc()
    elif t == "interface_role_change":
        dr_changes.labels(m["router"], m["interface"], m["state"]).inc()


def on_config(m):
    c = m.get("concept") or "n/a"
    config_changes.labels(m["scenario"], c, m["mode"], m["result"]).inc()
    config_last.labels(m["scenario"], c, m["mode"]).set(ts(m["ts"]))
    if m.get("duration") is not None:
        config_dur.labels(m["scenario"]).set(m["duration"])


HANDLERS = {T_SNAP: on_snapshot, T_EVENTS: on_event, T_CONFIG: on_config}


def main():
    start_http_server(9108)
    c = Consumer({
        "bootstrap.servers": BOOTSTRAP, "group.id": "ospf-exporter",
        "auto.offset.reset": "earliest", "enable.auto.commit": True,
        "allow.auto.create.topics": True,
    })
    c.subscribe(list(HANDLERS))
    log.info("consuming %s from %s, metrics on :9108", list(HANDLERS), BOOTSTRAP)
    while True:
        msg = c.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            log.debug("kafka: %s", msg.error())
            continue
        try:
            HANDLERS[msg.topic()](json.loads(msg.value()))
            consumed.labels(msg.topic()).inc()
        except Exception:  # noqa: BLE001
            log.exception("bad message on %s", msg.topic())


if __name__ == "__main__":
    main()
