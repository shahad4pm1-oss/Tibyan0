"""Shared setup for build scripts: make the backend package importable."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_DB = ROOT / "data" / "indexes" / "tibyan.sqlite3"
INDEX_DIR = ROOT / "data" / "indexes"
META_DIR = ROOT / "data" / "metadata"
