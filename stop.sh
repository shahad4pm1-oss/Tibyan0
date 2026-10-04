#!/usr/bin/env bash
# Stop the processes recorded by start.sh (.run/*.pid) only.
cd "$(dirname "$0")"
n_stopped=0
for n in frontend backend; do
  f=".run/$n.pid"; [ -f "$f" ] || continue
  pid="$(cut -d' ' -f1 "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null; for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    echo "Stopped $n (process $pid)"; n_stopped=$((n_stopped+1))
  fi
  rm -f "$f"
done
[ "$n_stopped" -eq 0 ] && echo "Tibyan was not running." || echo "Tibyan stopped."
