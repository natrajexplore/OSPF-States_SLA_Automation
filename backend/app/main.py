from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import bus, kafka_tail, monitor, scenarios
from . import devices as dev_mod
from .config import settings
from .eveng import EveNGClient, EveNGError
from .events import subscribe, unsubscribe
from .inventory import build_devices


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = []
    if settings.monitor_enabled:
        tasks.append(asyncio.create_task(monitor.run_forever()))
    if settings.kafka_bootstrap:
        tasks.append(asyncio.create_task(kafka_tail.run_forever()))
    yield
    for t in tasks:
        t.cancel()
    bus.flush()


app = FastAPI(title="ospf-sla-executor", lifespan=lifespan)
_eve = EveNGClient()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/config")
def public_config() -> dict:
    return {"grafana_url": settings.grafana_url, "kafka_enabled": bool(settings.kafka_bootstrap),
            "poll_interval": settings.poll_interval}


@app.get("/api/monitor/state")
def monitor_state() -> list[dict]:
    return monitor.snapshot()


@app.get("/api/events/recent")
def events_recent() -> list[dict]:
    return list(bus.RECENT)


@app.get("/api/events/stream")
async def events_stream() -> StreamingResponse:
    q = subscribe(bus.UI_CHANNEL)

    async def gen():
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    return
                yield f"event: ospf\ndata: {msg['data']}\n\n"
        finally:
            unsubscribe(bus.UI_CHANNEL, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/kafka/recent")
def kafka_recent() -> dict:
    return {"topics": kafka_tail.topics(), "counts": dict(kafka_tail.COUNTS), "messages": list(kafka_tail.RECENT)}


@app.get("/api/kafka/stream")
async def kafka_stream() -> StreamingResponse:
    q = subscribe(kafka_tail.KAFKA_CHANNEL)

    async def gen():
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    return
                yield f"event: kafka\ndata: {msg['data']}\n\n"
        finally:
            unsubscribe(kafka_tail.KAFKA_CHANNEL, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/devices")
def devices() -> list[dict]:
    devs = build_devices(_eve)
    return [
        {"name": d.name, "role": d.role, "mgmt_ip": d.mgmt_ip, "router_id": d.router_id, "status": d.status,
         "console": f"{d.console_host}:{d.console_port}" if d.console else None}
        for d in devs.values()
    ]


@app.get("/api/topology")
def topology() -> dict:
    devs = build_devices(_eve)
    nodes = [{"name": d.name, "role": d.role, "status": d.status} for d in devs.values()]
    try:
        links = [{"source": i.get("source_label") or i.get("source"),
                  "target": i.get("destination_label") or i.get("destination")} for i in _eve.topology()]
    except EveNGError as exc:
        return {"nodes": nodes, "links": [], "warning": str(exc)}
    return {"nodes": nodes, "links": links}


_SHOW_ALLOWED = [re.compile(p) for p in (
    r"show ip ospf",
    r"show ip ospf neighbor(?: detail)?",
    r"show ip ospf interface(?: brief| [\w/.-]{1,20})?",
    r"show ip ospf database(?: [a-z-]{1,20})?",
    r"show ip ospf border-routers",
    r"show ip route(?: ospf| \d{1,3}(?:\.\d{1,3}){3})?",
    r"show ip sla statistics",
    r"show bfd neighbors(?: details)?",
    r"show running-config \| section router ospf",
)]


@app.get("/api/devices/{name}/show")
def device_show(name: str, cmd: str) -> dict:
    """Read-only `show`. Whitelisted; nothing that can change config."""
    devs = build_devices()
    if name not in devs:
        raise HTTPException(404, name)
    cmd = " ".join(cmd.split())
    if len(cmd) > 120 or not any(p.fullmatch(cmd) for p in _SHOW_ALLOWED):
        raise HTTPException(400, "command not allowed (read-only OSPF/route show commands only)")
    return {"device": name, "command": cmd, "output": dev_mod.show(devs[name], cmd)}


@app.get("/api/scenarios")
def scenario_list() -> list[dict]:
    return scenarios.list_scenarios()


@app.post("/api/scenarios/{sid}/run")
async def scenario_run(sid: str) -> dict:
    try:
        return {"run_id": await scenarios.run_scenario(sid, rollback=False)}
    except FileNotFoundError:
        raise HTTPException(404, sid)


@app.post("/api/scenarios/{sid}/rollback")
async def scenario_rollback(sid: str) -> dict:
    try:
        return {"run_id": await scenarios.run_scenario(sid, rollback=True)}
    except FileNotFoundError:
        raise HTTPException(404, sid)


@app.post("/api/lab/reset")
async def lab_reset(nodes: list[str] | None = None) -> dict:
    return {"run_id": await scenarios.reset_baseline(nodes)}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    if run_id not in scenarios.RUNS:
        raise HTTPException(404, run_id)
    return scenarios.RUNS[run_id]


@app.get("/api/stream/{run_id}")
async def stream(run_id: str) -> StreamingResponse:
    q = subscribe(run_id)

    async def gen():
        try:
            # replay terminal state if the run already finished
            if run_id in scenarios.RUNS and scenarios.RUNS[run_id]["state"] != "running":
                yield f"event: result\ndata: {scenarios.RUNS[run_id]['state']}\n\n"
                return
            # replay lines logged before this client attached; everything queued so far is already in that snapshot
            backlog = list(scenarios.RUNS.get(run_id, {}).get("log", []))
            while not q.empty():
                q.get_nowait()
            for line in backlog:
                yield f"event: log\ndata: {json.dumps(line)}\n\n"
            while True:
                msg = await q.get()
                if msg is None:
                    yield "event: end\ndata: end\n\n"
                    return
                yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        finally:
            unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
