#!/usr/bin/env bash
# Drive one standalone OSPF lab (labs/<NN_topic>/) on the EVE-NG VM. Run it ON THE VM, from the repository checkout:
#
#   labs/labtool.sh <lab> import                 copy <lab>.unl into EVE-NG (/opt/unetlab/labs)
#   labs/labtool.sh <lab> start | stop           start / stop every node of that lab through the EVE API
#   labs/labtool.sh <lab> bootstrap [NODE ...]   one-time console bring-up (hostname, SSH, MGMT) of every node
#   labs/labtool.sh <lab> baseline [NODE ...]    push baseline/<NODE>.cfg to every node (also a "reset to baseline")
#   labs/labtool.sh <lab> health                 ping, SSH and FULL-neighbor count per router
#   labs/labtool.sh <lab> apply | rollback <id>  run a scenario from the lab's scenarios/ folder, with verification
#   labs/labtool.sh <lab> show <NODE> "<cmd>"    read-only show command
#   labs/labtool.sh <lab> capture <id>           the lab's probes.txt commands before, after apply and after rollback
#   labs/labtool.sh <lab> up                     import + start + bootstrap + baseline, then wait for OSPF to converge
#   labs/labtool.sh main <command> [args]        the same commands for the shared lab (/ospf-sla.unl, backend/)
#
# Every lab uses the same node ids and management addresses (192.168.99.11-14) as the shared lab, so only ONE lab may
# run at a time. Stop the shared lab and the dashboard (its monitor polls the same addresses, and it holds the EVE session) first:
#   labs/labtool.sh main stop ; docker stop ospf-sla-executor
# and bring them back afterwards:
#   labs/labtool.sh <lab> stop ; labs/labtool.sh main start ; docker start ospf-sla-executor
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB="${1:?usage: labtool.sh <lab|main> <command> [args]}"; CMD="${2:?missing command}"; shift 2

if [ "$LAB" = "main" ]; then
  LABDIR="$ROOT/backend"; UNL="$ROOT/labs/ospf-sla.unl"; EVENAME="ospf-sla"
else
  LABDIR="$ROOT/labs/$LAB"; [ -d "$LABDIR" ] || { echo "no such lab folder: $LABDIR" >&2; exit 2; }
  UNL="$LABDIR/$LAB.unl"; EVENAME="$LAB"
fi

# a throwaway container from the dashboard image, pointed at this lab's files (no backend code changes needed)
dock() {
  docker run --rm -i --network host --env-file "$ROOT/.env" \
    -v "$LABDIR:/lab:ro" -v "$ROOT/backend/scripts:/app/scripts:ro" \
    -e OSPF_INVENTORY=/lab/inventory.yaml -e OSPF_BASELINE=/lab/baseline \
    -e OSPF_SCENARIOS=/lab/scenarios -e OSPF_TEMPLATES=/lab/templates \
    -e OSPF_LAB_PATH="/$EVENAME.unl" -e OSPF_MONITOR=false -e OSPF_KAFKA_BOOTSTRAP= -e OSPF_RUNS=/tmp/runs \
    ospf-sla-executor:latest "$@"
}

nodes() {  # $1 = start | stop
  dock python - "$1" <<'PY'
import sys, time
from app.eveng import EveNGClient
c = EveNGClient(); action = sys.argv[1]
nodes = c.enrich()
for name, v in sorted(nodes.items(), key=lambda kv: int(kv[1]["id"])):
    (c.start_node if action == "start" else c.stop_node)(v["id"]); print(f"{action} {name}"); time.sleep(2 if action == "start" else 0)
time.sleep(8)
print({n: v["status"] for n, v in c.enrich().items()})
PY
}

snap() {  # $1 = label; runs every probes.txt line (NODE|command)
  echo "########## $1"
  while IFS='|' read -r d c; do
    [ -z "$d" ] && continue; echo "--- $d# $c"
    { dock python scripts/run_scenario.py show "$d" "$c" </dev/null 2>&1 || { sleep 20; dock python scripts/run_scenario.py show "$d" "$c" </dev/null 2>&1; }; } || true
  done < "$LABDIR/probes.txt"
}

case "$CMD" in
  import)
    dst="/opt/unetlab/labs/$EVENAME.unl"
    cp "$UNL" "$dst"; chown www-data:www-data "$dst"; chmod 644 "$dst"; echo "imported $dst" ;;
  start|stop) nodes "$CMD" ;;
  bootstrap)  dock python scripts/bootstrap.py "$@" ;;
  baseline)   dock python scripts/push_baseline.py "$@" ;;
  health)     dock python scripts/healthcheck.py ;;
  apply|rollback|show) dock python scripts/run_scenario.py "$CMD" "$@" ;;
  up)
    "$0" "$LAB" import; "$0" "$LAB" start; sleep 75
    "$0" "$LAB" bootstrap; "$0" "$LAB" baseline; sleep 60
    "$0" "$LAB" health || true; echo "lab $LAB is up" ;;
  capture)
    SID="${1:?usage: labtool.sh <lab> capture <scenario-id>}"
    [ -f "$LABDIR/probes.txt" ] || { echo "no probes.txt in $LABDIR" >&2; exit 2; }
    snap BASELINE
    echo "########## APPLY $SID";    dock python scripts/run_scenario.py apply "$SID" </dev/null 2>&1 || true
    snap APPLIED
    echo "########## ROLLBACK $SID"; dock python scripts/run_scenario.py rollback "$SID" </dev/null 2>&1 || true
    snap ROLLED_BACK
    echo DONE ;;
  *) echo "unknown command: $CMD" >&2; exit 2 ;;
esac
