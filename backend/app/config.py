from __future__ import annotations

import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent          # /app
INVENTORY_PATH = Path(os.getenv("OSPF_INVENTORY", BASE_DIR / "inventory.yaml"))
TEMPLATE_DIR = Path(os.getenv("OSPF_TEMPLATES", BASE_DIR / "templates"))
SCENARIO_DIR = Path(os.getenv("OSPF_SCENARIOS", BASE_DIR / "scenarios"))
BASELINE_DIR = Path(os.getenv("OSPF_BASELINE", BASE_DIR / "baseline"))
RUNS_DIR = Path(os.getenv("OSPF_RUNS", BASE_DIR / "runs"))
# the standalone labs (labs/NN_topic/): mounted at /app/labs in the container, ../labs when run from a checkout
LABS_DIR = Path(os.getenv("OSPF_LABS_DIR", BASE_DIR / "labs" if (BASE_DIR / "labs").is_dir() else BASE_DIR.parent / "labs"))
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Simulation mode: an in-process model of the routers instead of EVE-NG + SSH (app/sim/). For demos and tests.
    simulate = _bool("OSPF_SIMULATE", "false")
    sim_settle_scale = float(os.getenv("OSPF_SIM_SETTLE_SCALE", "0.1"))   # scenario settle_seconds x this in simulation
    sim_converge = float(os.getenv("OSPF_SIM_CONVERGE", "4"))             # seconds an adjacency takes to reach FULL

    eveng_url = os.getenv("OSPF_EVENG_URL", "http://127.0.0.1")
    eveng_user = os.getenv("OSPF_EVENG_USER", "admin")
    eveng_pass = os.getenv("OSPF_EVENG_PASS", "eve")
    lab_path = os.getenv("OSPF_LAB_PATH", "/ospf-sla.unl")

    device_user = os.getenv("OSPF_DEVICE_USER", "lab")
    device_pass = os.getenv("OSPF_DEVICE_PASS", "lab123")
    device_secret = os.getenv("OSPF_DEVICE_SECRET", os.getenv("OSPF_DEVICE_PASS", "lab123"))
    console_fallback = _bool("OSPF_CONSOLE_FALLBACK", "true")
    # refuse to configure a router whose prompt is not its inventory name (a wrong IP would otherwise hit another box)
    hostname_guard = _bool("OSPF_HOSTNAME_GUARD", "true")
    connect_retries = int(os.getenv("OSPF_CONNECT_RETRIES", "2"))

    # Kafka runs on Docker Desktop (Windows host); empty bootstrap disables publishing.
    kafka_bootstrap = os.getenv("OSPF_KAFKA_BOOTSTRAP", "")
    topic_events = os.getenv("OSPF_TOPIC_EVENTS", "ospf.neighbor.events")
    topic_snapshots = os.getenv("OSPF_TOPIC_SNAPSHOTS", "ospf.neighbor.snapshots")
    topic_config = os.getenv("OSPF_TOPIC_CONFIG", "ospf.config.changes")
    poll_interval = float(os.getenv("OSPF_POLL_INTERVAL", "3" if simulate else "20"))
    monitor_enabled = _bool("OSPF_MONITOR", "true")
    grafana_url = os.getenv("OSPF_GRAFANA_URL", "")
    kafka_ui_url = os.getenv("OSPF_KAFKA_UI_URL", "")
    prometheus_url = os.getenv("OSPF_PROMETHEUS_URL", "")

    conn_timeout = int(os.getenv("OSPF_CONN_TIMEOUT", "15"))
    read_timeout = int(os.getenv("OSPF_READ_TIMEOUT", "30"))


settings = Settings()


def load_inventory() -> dict:
    with open(INVENTORY_PATH) as fh:
        return yaml.safe_load(fh)
