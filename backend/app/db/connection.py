from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    p = Path(path)
    if readonly:
        if not p.exists():
            raise FileNotFoundError(str(p))
        # as_uri() gives file:///C:/... on Windows and percent-encodes spaces / non-ASCII folder names
        conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
