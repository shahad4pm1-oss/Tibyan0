#!/usr/bin/env bash
# Tibyan one-time setup for Linux/macOS (Windows: use setup.ps1 / setup.cmd). Safe to run again.
# Options: --rebuild (rebuild corpus), --dev (also install pytest/ruff),
#          --keep-venv (keep an existing backend/.venv that uses a different SUPPORTED Python than the one selected)
# Python: 3.11 recommended (tried first); 3.12, 3.13 and 3.14 also supported.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"; REBUILD=0; DEV=0; KEEP_VENV=0
for a in "$@"; do case "$a" in --rebuild) REBUILD=1;; --dev) DEV=1;; --keep-venv) KEEP_VENV=1;; esac; done
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
stop() { echo; echo "STOPPED: $*" >&2; echo; exit 1; }
step() { echo "==> $*"; }
warn() { echo "    !!  $*"; }
SUPPORTED="3.11 3.12 3.13 3.14"
is_supported() { case " $SUPPORTED " in *" $1 "*) return 0;; esac; return 1; }

step "Checking Python (3.11 recommended; 3.12, 3.13 and 3.14 also supported)"
PY=""; PYVER=""
for c in python3.11 python3.12 python3.13 python3.14 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    if is_supported "$v"; then PY="$c"; PYVER="$v"; echo "    OK  Python $v ($c)"; break; fi
  fi
done
[ -n "$PY" ] || stop "No supported Python found (3.11 recommended; 3.12, 3.13 or 3.14 also work). Install Python 3.11 and run ./setup.sh again."
[ "$PYVER" = "3.11" ] || warn "Using Python $PYVER (supported). Python 3.11 is the recommended version for the competition build."

step "Checking Node.js (20.19+ or 22.12+)"
command -v node >/dev/null 2>&1 || stop "Node.js not found. Install Node.js 22 LTS and run ./setup.sh again."
NV="$(node --version | sed 's/^v//')"; MAJ="${NV%%.*}"; MIN="$(echo "$NV" | cut -d. -f2)"
if ! { [ "$MAJ" -eq 20 ] && [ "$MIN" -ge 19 ]; } && ! { [ "$MAJ" -eq 22 ] && [ "$MIN" -ge 12 ]; } && [ "$MAJ" -lt 23 ] && [ "$MAJ" -ne 21 ]; then
  stop "Node.js $NV is too old. Install Node.js 22 LTS."
fi
echo "    OK  Node.js $NV"

VENV="$ROOT/backend/.venv"; VPY="$VENV/bin/python"; OLD=""; OLDVER=""; VENVVER="$PYVER"
# On failure during a rebuild, put the previous environment back unchanged, then stop.
stop_py() {
  if [ -n "$OLD" ] && [ -d "$OLD" ]; then rm -rf "$VENV"; mv "$OLD" "$VENV"; warn "The previous backend/.venv (Python $OLDVER) was restored unchanged."; fi
  stop "$*"
}
if [ -d "$VENV" ]; then
  step "Checking the existing Python environment backend/.venv"
  VV="$("$VPY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  WHY=""
  if [ -z "$VV" ]; then WHY="its Python does not run (the Python it was created with may have been removed or moved)"
  elif ! is_supported "$VV"; then WHY="it uses Python $VV, which Tibyan does not support"
  elif [ "$VV" != "$PYVER" ]; then
    if [ "$KEEP_VENV" -eq 1 ]; then warn "backend/.venv uses Python $VV, not the selected Python $PYVER: kept because of --keep-venv."; VENVVER="$VV"
    else WHY="it uses Python $VV, but setup selected Python $PYVER"; fi
  else echo "    OK  backend/.venv uses Python $VV"; fi
  if [ -n "$WHY" ]; then
    warn "backend/.venv will be rebuilt: $WHY."
    if [ -n "$VV" ] && is_supported "$VV"; then warn "To keep Python $VV instead, run: ./setup.sh --keep-venv"; fi
    if [ -f .run/backend.pid ] && kill -0 "$(cut -d' ' -f1 .run/backend.pid)" 2>/dev/null; then
      stop "Tibyan is running from this environment. Stop it first (./stop.sh), then run setup again."
    fi
    mkdir -p .run; OLD="$ROOT/.run/venv-previous"; rm -rf "$OLD"
    mv "$VENV" "$OLD" || { OLD=""; stop "Could not move the old backend/.venv aside."; }
    OLDVER="${VV:-unknown}"
  fi
fi
if [ ! -d "$VENV" ]; then step "Creating backend/.venv (Python $PYVER)"; "$PY" -m venv "$VENV" || stop_py "Could not create backend/.venv"; fi
step "Installing Python packages (pinned)"
"$VPY" -m pip install --disable-pip-version-check -q -r backend/requirements.txt -c backend/constraints.txt || stop_py "pip install failed"
if [ "$DEV" -eq 1 ]; then "$VPY" -m pip install --disable-pip-version-check -q -r backend/requirements-dev.txt -c backend/constraints.txt || stop_py "dev tools install failed"; fi
"$VPY" -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')" || stop_py "This Python's SQLite lacks FTS5."
if [ -n "$OLD" ] && [ -d "$OLD" ]; then rm -rf "$OLD"; OLD=""; echo "    OK  backend/.venv rebuilt with Python $PYVER (previous environment removed)"; fi
echo "    OK  Python packages installed (Python $VENVVER)"

LOCKSHA="$("$VPY" -c "import hashlib;print(hashlib.sha256(open('frontend/package-lock.json','rb').read()).hexdigest().upper())")"
if [ -f frontend/node_modules/.tibyan-lock-sha256 ] && [ "$(cat frontend/node_modules/.tibyan-lock-sha256)" = "$LOCKSHA" ] && [ -f frontend/node_modules/vite/bin/vite.js ]; then
  echo "    OK  frontend packages already installed (package-lock.json unchanged)"
else
  step "Installing frontend packages (npm ci)"
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error) || stop "npm ci failed"
  echo "$LOCKSHA" > frontend/node_modules/.tibyan-lock-sha256
fi

[ -f .env ] || { cp .env.example .env; echo "    OK  created .env from .env.example (LLM_UNAVAILABLE mode)"; }
mkdir -p data/raw data/indexes logs .run

DB="$ROOT/data/indexes/tibyan.sqlite3"
NEED=$REBUILD
if [ "$NEED" -eq 0 ] && [ -f "$DB" ]; then
  step "Validating existing corpus"
  "$VPY" scripts/validate_corpus.py >/dev/null || { echo "    !!  validation failed: rebuilding"; NEED=1; }
elif [ ! -f "$DB" ]; then NEED=1; fi
if [ "$NEED" -eq 1 ]; then
  step "Downloading verified source files and building the corpus"
  if ! "$VPY" scripts/build_corpus.py; then
    echo "Place the source files manually (SHA-256 in docs/LOCAL_DATA_MANIFEST.md) and run ./setup.sh again:" >&2
    echo "  data/raw/kfgqpc/UthmanicHafs_v2-0.zip" >&2
    echo "  data/raw/openiti/0256Bukhari.Sahih.Shamela0001681-ara1" >&2
    echo "  data/raw/openiti/0261Muslim.Sahih.Shamela0001727-ara1.mARkdown" >&2
    stop "Corpus build failed."
  fi
fi
step "Sanity check"
"$VPY" scripts/sanity_check.py || stop "Sanity check failed. Run ./setup.sh --rebuild"
echo; echo "Setup complete. Start with: ./start.sh"
