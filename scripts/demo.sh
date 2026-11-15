#!/usr/bin/env bash
# Run the dashboard in simulation mode without Docker: backend on :8010, UI on http://localhost:5173.
#   ./scripts/demo.sh        (Python 3.11+ and Node 18+; creates backend/.venv-demo the first time; Ctrl+C stops both)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
venv="$root/backend/.venv-demo"
if [ ! -d "$venv" ]; then
  python3 -m venv "$venv"
  "$venv/bin/pip" install -q -r "$root/backend/requirements.txt"
fi
export OSPF_SIMULATE=true OSPF_KAFKA_BOOTSTRAP=""
(cd "$root/backend" && "$venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8010) &
backend=$!
trap 'kill $backend 2>/dev/null' EXIT
cd "$root/frontend"
[ -d node_modules ] || npm ci
echo -e "\nOpen http://localhost:5173  (simulation mode)\n"
VITE_API=http://127.0.0.1:8010 npx vite --port 5173
