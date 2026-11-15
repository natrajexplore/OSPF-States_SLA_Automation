from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import bus, kafka_tail, labinfo, monitor, scenarios
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
    ssh_servers = []
    if settings.simulate and settings.sim_ssh:
        from .sim import sshd
        ssh_servers = await sshd.start()
    yield
    for t in tasks:
        t.cancel()
    for srv in ssh_servers:
        srv.close()
    bus.flush()


app = FastAPI(title="ospf-sla-executor", lifespan=lifespan)
if settings.simulate:
    from .sim.driver import SimEveClient
    _eve = SimEveClient()
else:
    _eve = EveNGClient()

_SID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """API answers are live state: never let a browser or proxy serve a stale copy."""
    resp = await call_next(request)
    if request.url.path.startswith("/api/") and "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/config")
def public_config() -> dict:
    return {"grafana_url": settings.grafana_url, "kafka_ui_url": settings.kafka_ui_url,
            "prometheus_url": settings.prometheus_url, "kafka_enabled": bool(settings.kafka_bootstrap),
            "poll_interval": settings.poll_interval, "simulate": settings.simulate,
            "mode": "simulation" if settings.simulate else "eve-ng"}


@app.get("/api/prometheus/query")
def prometheus_query(query: str) -> dict:
    """Thin proxy for a PromQL instant query, so the browser doesn't need direct network access to
    Prometheus (it runs on the Windows host; the UI is served from the EVE-NG VM)."""
    if not settings.prometheus_query_url:
        raise HTTPException(503, "OSPF_PROMETHEUS_URL is not set")
    try:
        r = httpx.get(f"{settings.prometheus_query_url}/api/v1/query", params={"query": query}, timeout=10.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Prometheus unreachable: {exc}")
    return r.json()


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


@app.get("/api/graph")
def lab_graph() -> dict:
    """Routers, tiers and links of the shared lab, for the 3D views (live state comes from /api/monitor/state)."""
    return labinfo.graph()


@app.get("/api/credentials")
def credentials() -> dict:
    """Login, password and enable secret of every router of every lab, checked against its baseline. Read by the
    Credentials tab and scripts/putty-setup.ps1. Anyone who can open the dashboard can read them: fine for a private lab VM."""
    return {"labs": labinfo.credentials()}


@app.get("/api/putty")
def putty_sessions() -> dict:
    """What the PuTTY tab and scripts/putty-setup.ps1 need: one SSH session per router. In simulation mode the routers
    are the backend's SSH servers (127.0.0.1:2201...); on the real lab they are the routers' management addresses,
    reached through the EVE-NG VM (a jump host, because 192.168.99.x only exists inside the VM)."""
    from urllib.parse import urlparse
    out = []
    if settings.simulate:
        if settings.sim_ssh:
            from .sim import sshd
            for name, lg in sshd.logins().items():
                out.append({"lab": "sim", "router": name, "host": settings.sim_ssh_host, "port": lg["port"],
                            "username": lg["username"], "password": lg["password"], "secret": lg["secret"],
                            "jump": None, "kex": None})
        return {"mode": "simulation", "enabled": settings.sim_ssh, "sessions": out,
                "fingerprint": sshd.fingerprint() if settings.sim_ssh else "",
                "putty_hostkey": sshd.putty_hostkey() if settings.sim_ssh else ""}
    vm = urlparse(settings.eveng_url).hostname or ""
    for lab in labinfo.credentials():
        for r in lab["routers"]:
            out.append({"lab": lab["id"], "router": r["name"], "host": r["mgmt_ip"], "port": 22,
                        "username": settings.putty_user, "password": r["password"], "secret": r["secret"],
                        "jump": vm, "kex": "ios15"})
    return {"mode": "eve-ng", "enabled": True, "sessions": out, "fingerprint": ""}


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
    # OSPFv3 (scenarios 17-18)
    r"show ipv6 ospf(?: neighbor(?: detail)?| interface(?: brief| [\w/.-]{1,20})?| database(?: [a-z-]{1,20})?| border-routers)?",
    r"show ipv6 route(?: ospf| [0-9a-fA-F:]{2,39}(?:/\d{1,3})?)?",
    r"show ipv6 interface brief",
    r"show running-config \| section ipv6 router ospf",
    # any other read-only show, abbreviations allowed, with one IOS output filter; no `;`, no show tech-support
    r"sh(?:o|ow)? (?!tech)[A-Za-z0-9][A-Za-z0-9 ./:_-]{0,80}"
    r"(?: \| (?:i|in|inc|incl|include|e|ex|exc|exclude|b|be|begin|s|se|sec|section|c|co|count) [A-Za-z0-9 ./:_^$*+?()\[\]-]{0,60})?",
)]


@app.get("/api/devices/{name}/show")
def device_show(name: str, cmd: str) -> dict:
    """Read-only `show`. Whitelisted; nothing that can change config."""
    devs = build_devices()
    if name not in devs:
        raise HTTPException(404, name)
    cmd = " ".join(cmd.split())
    if len(cmd) > 120 or not any(p.fullmatch(cmd) for p in _SHOW_ALLOWED):
        raise HTTPException(400, "command not allowed (read-only show commands only; use PuTTY to configure)")
    try:
        output = dev_mod.show(devs[name], cmd)
    except Exception as exc:  # noqa: BLE001 - SSH/console failure: report it instead of a bare 500
        raise HTTPException(502, f"{name}: {exc}")
    return {"device": name, "command": cmd, "output": output}


@app.get("/api/scenarios")
def scenario_list() -> list[dict]:
    return scenarios.list_scenarios()


def _check_sid(sid: str) -> None:
    if not _SID.match(sid):
        raise HTTPException(400, "invalid scenario id")


@app.post("/api/scenarios/{sid}/run")
async def scenario_run(sid: str) -> dict:
    _check_sid(sid)
    try:
        return {"run_id": await scenarios.run_scenario(sid, rollback=False)}
    except FileNotFoundError:
        raise HTTPException(404, sid)
    except scenarios.TargetsBusy as exc:
        raise HTTPException(409, str(exc))
    except scenarios.ScenarioError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/scenarios/{sid}/rollback")
async def scenario_rollback(sid: str) -> dict:
    _check_sid(sid)
    try:
        return {"run_id": await scenarios.run_scenario(sid, rollback=True)}
    except FileNotFoundError:
        raise HTTPException(404, sid)
    except scenarios.TargetsBusy as exc:
        raise HTTPException(409, str(exc))
    except scenarios.ScenarioError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/lab/reset")
async def lab_reset(nodes: list[str] | None = None) -> dict:
    try:
        return {"run_id": await scenarios.reset_baseline(nodes)}
    except scenarios.TargetsBusy as exc:
        raise HTTPException(409, str(exc))
    except scenarios.ScenarioError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    if run_id not in scenarios.RUNS:
        raise HTTPException(404, run_id)
    return scenarios.RUNS[run_id]


@app.get("/api/stream/{run_id}")
async def stream(run_id: str) -> StreamingResponse:
    if run_id not in scenarios.RUNS:
        raise HTTPException(404, run_id)          # an unknown id would otherwise hold the stream open forever
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
