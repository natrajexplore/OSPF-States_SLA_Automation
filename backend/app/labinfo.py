"""Read-only views of the lab files: the topology graph for the 3D views, and the router logins of the shared lab and of
every standalone lab (labs/NN_topic/) for the Credentials tab and scripts/putty-setup.ps1."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .config import BASELINE_DIR, INVENTORY_PATH, LABS_DIR, load_inventory, settings

TIER = {"backbone": 2, "abr": 1}                   # anything else (internal-area1) is tier 0, the bottom of the 3D view
_ENABLE = re.compile(r"^enable secret (?:\d\s+)?(\S+)", re.M)
_USER = re.compile(r"^username (\S+) .*?secret (?:\d\s+)?(\S+)", re.M)


def _ifname(short: str) -> str:
    """e1/0 -> Ethernet1/0, fa0/0 -> FastEthernet0/0 (the names `show ip ospf neighbor` prints)."""
    m = re.fullmatch(r"(?i)(fa|e)(\d+/\d+)", short)
    return (("FastEthernet" if m.group(1).lower() == "fa" else "Ethernet") + m.group(2)) if m else short


def graph() -> dict:
    """The shared lab as the 3D views draw it: routers with their tier, and links (2 members = point-to-point, more = a
    broadcast segment). An area-0 link joins only backbone routers and ABRs; any other link is in area 1."""
    inv = load_inventory()
    devs = inv["devices"]
    user = inv.get("defaults", {}).get("username", settings.device_user)
    nodes = [{"name": n, "role": d["role"], "tier": TIER.get(d["role"], 0), "router_id": d["router_id"],
              "mgmt_ip": str(d["mgmt_ip"]).split("/")[0], "username": d.get("username", user)} for n, d in devs.items()]
    links = []
    for ln in inv["links"]:
        members = [{"node": m["node"], "if": m["if"], "ifname": _ifname(m["if"])} for m in ln["members"]]
        area = 0 if all(devs[m["node"]]["role"] in TIER for m in members) else 1
        links.append({"name": ln["name"], "area": area, "members": members})
    return {"lab": inv["lab"]["name"], "nodes": nodes, "links": links}


def _baseline_login(baseline: Path, name: str) -> tuple[str, str, str] | None:
    f = baseline / f"{name}.cfg"
    if not f.is_file():
        return None
    text = f.read_text(encoding="utf-8")
    en, us = _ENABLE.search(text), _USER.search(text)
    return (us.group(1), us.group(2), en.group(1)) if en and us else None


def _lab(lab_id: str, title: str, inv_file: Path, baseline: Path, eve_path: str) -> dict:
    inv = yaml.safe_load(inv_file.read_text(encoding="utf-8"))
    d = inv.get("defaults", {})
    rows = []
    for name, spec in inv["devices"].items():
        # same precedence as inventory.build_devices(): per device, then defaults, then .env
        user = spec.get("username", d.get("username", settings.device_user))
        pw = spec.get("password", d.get("password", settings.device_pass))
        secret = spec.get("secret", d.get("secret", settings.device_secret))
        base = _baseline_login(baseline, name)
        rows.append({"name": name, "role": spec["role"], "router_id": spec["router_id"],
                     "mgmt_ip": str(spec["mgmt_ip"]).split("/")[0], "username": user, "password": pw, "secret": secret,
                     "baseline_match": base == (user, pw, secret) if base else None})
    return {"id": lab_id, "title": title, "eve_path": eve_path, "routers": rows}


def credentials() -> list[dict]:
    labs = [_lab("shared", "Shared 4-router lab (the dashboard's lab)", INVENTORY_PATH, BASELINE_DIR, settings.lab_path)]
    if LABS_DIR.is_dir():
        for d in sorted(p for p in LABS_DIR.iterdir() if (p / "inventory.yaml").is_file()):
            raw = (d / "inventory.yaml").read_text(encoding="utf-8")
            title = next((ln.split(":", 1)[1].strip() for ln in raw.splitlines() if ln.startswith("# Lab")), d.name)
            labs.append(_lab(d.name, title, d / "inventory.yaml", d / "baseline", f"/{d.name}.unl"))
    return labs
