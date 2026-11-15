"""The HTTP API in simulation mode: an apply and a rollback run end to end, plus input validation."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sim.driver import lab


@pytest.fixture(scope="module")
def client():
    lab().reset_all()
    with TestClient(app) as c:
        yield c


def _wait(client, run_id: str, timeout: float = 30) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        rec = client.get(f"/api/runs/{run_id}").json()
        if rec["state"] != "running":
            return rec
        time.sleep(0.2)
    raise AssertionError(f"{run_id} still running")


def test_config_reports_simulation(client):
    cfg = client.get("/api/config").json()
    assert cfg["simulate"] is True and cfg["mode"] == "simulation"
    assert client.get("/api/config").headers["cache-control"] == "no-store"


def test_devices_and_graph(client):
    devs = client.get("/api/devices").json()
    assert [d["name"] for d in devs] == ["R1", "R2", "R3", "R4"]
    assert all(d["status"] == "running" for d in devs)
    g = client.get("/api/graph").json()
    assert len(g["nodes"]) == 4 and len(g["links"]) == 3


def test_scenarios_listed(client):
    ids = [s["id"] for s in client.get("/api/scenarios").json()]
    assert len(ids) == 18 and ids[0] == "01_adjacency"


def test_apply_and_rollback_run(client):
    rec = _wait(client, client.post("/api/scenarios/07_cost_steering/run").json()["run_id"])
    assert rec["state"] == "passed", rec
    assert any("pushing to R4" in ln for ln in rec["log"])
    assert all(r["passed"] for r in rec["results"])
    rec = _wait(client, client.post("/api/scenarios/07_cost_steering/rollback").json()["run_id"])
    assert rec["state"] == "passed", rec


def test_reset_baseline(client):
    rec = _wait(client, client.post("/api/lab/reset").json()["run_id"])
    assert rec["state"] == "done"


def test_cli_whitelist(client):
    r = client.get("/api/devices/R3/show", params={"cmd": "show ip ospf neighbor"})
    assert r.status_code == 200 and "10.255.0.4" in r.json()["output"]
    assert client.get("/api/devices/R3/show", params={"cmd": "configure terminal"}).status_code == 400
    assert client.get("/api/devices/R3/show", params={"cmd": "show ip ospf neighbor ; reload"}).status_code == 400
    assert client.get("/api/devices/R3/show", params={"cmd": "show tech-support"}).status_code == 400
    r = client.get("/api/devices/R3/show", params={"cmd": "sh ip int br | inc Ethernet1/0"})
    assert r.status_code == 200 and "10.0.123.3" in r.json()["output"]
    assert "hostname R3" in client.get("/api/devices/R3/show", params={"cmd": "show running-config"}).json()["output"]
    assert client.get("/api/devices/R9/show", params={"cmd": "show ip ospf"}).status_code == 404


def test_bad_ids(client):
    assert client.post("/api/scenarios/nope/run").status_code == 404
    assert client.post("/api/scenarios/..%2Fx/run").status_code in (400, 404)
    assert client.get("/api/stream/does-not-exist").status_code == 404
    assert client.post("/api/lab/reset", json=["R9"]).status_code == 400


def test_credentials(client):
    labs = client.get("/api/credentials").json()["labs"]
    assert labs[0]["id"] == "shared" and len(labs[0]["routers"]) == 4
    assert all(r["baseline_match"] for r in labs[0]["routers"])
