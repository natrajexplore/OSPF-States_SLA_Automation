#!/usr/bin/env python
"""Reachability + OSPF neighbor count for every inventory device.

    docker exec -it ospf-sla-executor python scripts/healthcheck.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import devices as dev_mod            # noqa: E402
from app.eveng import EveNGClient             # noqa: E402
from app.inventory import build_devices       # noqa: E402


def ping(ip: str) -> bool:
    return subprocess.run(
        ["ping", "-c", "2", "-W", "1", ip],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def main() -> int:
    try:
        devs = build_devices(EveNGClient())
    except Exception:  # noqa: BLE001
        devs = build_devices()
    print(f"{'NODE':<10} {'MGMT IP':<16} {'EVE':<10} {'PING':<6} {'SSH':<6} OSPF")
    rc = 0
    for d in devs.values():
        p = "up" if ping(d.mgmt_ip) else "DOWN"
        ssh, ospf = "-", "-"
        try:
            out = dev_mod.show(d, "show ip ospf neighbor")
            ssh = "ok"
            ospf = f"{sum('FULL' in l for l in out.splitlines())} FULL"
        except Exception as exc:  # noqa: BLE001
            ssh = "FAIL"
            ospf = str(exc)[:40]
            rc = 1
        print(f"{d.name:<10} {d.mgmt_ip:<16} {d.status:<10} {p:<6} {ssh:<6} {ospf}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
