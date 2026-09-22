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
RUNS_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    eveng_url = os.getenv("OSPF_EVENG_URL", "http://127.0.0.1")
    eveng_user = os.getenv("OSPF_EVENG_USER", "admin")
    eveng_pass = os.getenv("OSPF_EVENG_PASS", "eve")
    lab_path = os.getenv("OSPF_LAB_PATH", "/ospf-sla.unl")

    device_user = os.getenv("OSPF_DEVICE_USER", "lab")
    device_pass = os.getenv("OSPF_DEVICE_PASS", "lab123")
    device_secret = os.getenv("OSPF_DEVICE_SECRET", os.getenv("OSPF_DEVICE_PASS", "lab123"))
    console_fallback = os.getenv("OSPF_CONSOLE_FALLBACK", "true").lower() == "true"

    # Kafka runs on Docker Desktop (Windows host); empty bootstrap disables publishing.
    kafka_bootstrap = os.getenv("OSPF_KAFKA_BOOTSTRAP", "")
    topic_events = os.getenv("OSPF_TOPIC_EVENTS", "ospf.neighbor.events")
    topic_snapshots = os.getenv("OSPF_TOPIC_SNAPSHOTS", "ospf.neighbor.snapshots")
    topic_config = os.getenv("OSPF_TOPIC_CONFIG", "ospf.config.changes")
    poll_interval = float(os.getenv("OSPF_POLL_INTERVAL", "20"))
    monitor_enabled = os.getenv("OSPF_MONITOR", "true").lower() == "true"
    grafana_url = os.getenv("OSPF_GRAFANA_URL", "")
    kafka_ui_url = os.getenv("OSPF_KAFKA_UI_URL", "")
    prometheus_url = os.getenv("OSPF_PROMETHEUS_URL", "")

    conn_timeout = int(os.getenv("OSPF_CONN_TIMEOUT", "15"))
    read_timeout = int(os.getenv("OSPF_READ_TIMEOUT", "30"))


settings = Settings()


def load_inventory() -> dict:
    with open(INVENTORY_PATH) as fh:
        return yaml.safe_load(fh)
