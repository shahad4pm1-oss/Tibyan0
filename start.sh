#!/usr/bin/env bash
# Start Tibyan (backend + frontend) in the background. Stop with ./stop.sh. Logs in logs/.
set -euo pipefail
cd "$(dirname "$0")"; ROOT="$(pwd)"
envget() { local v; v="$(grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/ #.*//; s/[[:space:]]*$//')"; echo "${v:-$2}"; }
BHOST="$(envget BACKEND_HOST 127.0.0.1)"; BPORT="$(envget BACKEND_PORT 8000)"; FPORT="$(envget FRONTEND_PORT 5173)"
VPY="$ROOT/backend/.venv/bin/python"
stop() { echo "STOPPED: $*" >&2; exit 1; }
[ -x "$VPY" ] || stop "Run ./setup.sh first."
[ -f data/indexes/tibyan.sqlite3 ] || stop "Corpus database missing. Run ./setup.sh first."
[ -f frontend/node_modules/vite/bin/vite.js ] || stop "Frontend packages missing. Run ./setup.sh first."
mkdir -p logs .run
for n in backend frontend; do
  if [ -f ".run/$n.pid" ] && kill -0 "$(cut -d' ' -f1 ".run/$n.pid")" 2>/dev/null; then stop "Tibyan is already running. Use ./stop.sh first."; fi
done
port_busy() { "$VPY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$1))==0 else 1)"; }
port_busy "$BPORT" && stop "Port $BPORT is in use (set BACKEND_PORT in .env)."
port_busy "$FPORT" && stop "Port $FPORT is in use (set FRONTEND_PORT in .env and CORS_ORIGINS)."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 VITE_API_BASE_URL="http://localhost:$BPORT"
(cd backend && exec "$VPY" -m uvicorn app.main:app --host "$BHOST" --port "$BPORT" --no-server-header >"$ROOT/logs/backend.out.log" 2>"$ROOT/logs/backend.err.log") &
echo "$! 0" > .run/backend.pid
(cd frontend && exec node node_modules/vite/bin/vite.js --port "$FPORT" --strictPort --host 127.0.0.1 >"$ROOT/logs/frontend.out.log" 2>"$ROOT/logs/frontend.err.log") &
echo "$! 0" > .run/frontend.pid
wait_http() { for _ in $(seq 1 120); do curl -s -o /dev/null "$1" && return 0; sleep 0.7; done; return 1; }
wait_http "http://127.0.0.1:$BPORT/health" || { tail -20 logs/backend.err.log; ./stop.sh >/dev/null; stop "Backend failed to start."; }
wait_http "http://127.0.0.1:$FPORT/" || { tail -20 logs/frontend.err.log; ./stop.sh >/dev/null; stop "Frontend failed to start."; }
H="$(curl -s "http://127.0.0.1:$BPORT/health")"
MODE="$(echo "$H" | "$VPY" -c 'import json,sys; print(json.load(sys.stdin)["llm_mode"])')"
echo
echo "Tibyan is running."
echo "  Frontend URL : http://localhost:$FPORT"
echo "  Backend URL  : http://localhost:$BPORT"
echo "  Health URL   : http://localhost:$BPORT/health"
echo "  LLM mode     : $MODE"
echo "  Stop with    : ./stop.sh"
