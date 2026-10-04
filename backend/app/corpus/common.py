from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SourceRecord:
    id: str
    source_type: str
    title: str
    edition: str
    license_note: str
    verification_status: str
    acquired_at: str
    corpus_version: str
    author: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PassageRecord:
    id: str
    source_id: str
    reference: str
    sequence: int
    parent_id: str | None
    original_text: str
    normalized_text: str
    normalized_text_alt: str | None = None
    metadata: dict = field(default_factory=dict)


def insert_source(conn: sqlite3.Connection, s: SourceRecord) -> None:
    conn.execute(
        """INSERT INTO sources (id, source_type, title, author, edition, publisher, source_url,
           license_note, verification_status, acquired_at, corpus_version, metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (s.id, s.source_type, s.title, s.author, s.edition, s.publisher, s.source_url, s.license_note,
         s.verification_status, s.acquired_at, s.corpus_version, json.dumps(s.metadata, ensure_ascii=False)),
    )


def next_rowid(conn: sqlite3.Connection) -> int:
    return (conn.execute("SELECT COALESCE(MAX(rowid_int), 0) FROM passages").fetchone()[0]) + 1


def insert_passages(conn: sqlite3.Connection, passages: list[PassageRecord]) -> None:
    start = next_rowid(conn)
    conn.executemany(
        """INSERT INTO passages (id, rowid_int, source_id, reference, sequence, parent_id, original_text,
           normalized_text, normalized_text_alt, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (p.id, start + i, p.source_id, p.reference, p.sequence, p.parent_id, p.original_text,
             p.normalized_text, p.normalized_text_alt, json.dumps(p.metadata, ensure_ascii=False))
            for i, p in enumerate(passages)
        ],
    )


def link_sequential(conn: sqlite3.Connection, ordered_ids_by_group: dict[str, list[str]]) -> None:
    """previous/next links inside each group (e.g. each surah). Never across groups."""
    rows = []
    for ids in ordered_ids_by_group.values():
        for a, b in pairwise(ids):
            rows.append((a, b, "next", 1))
            rows.append((b, a, "previous", 1))
    conn.executemany(
        "INSERT INTO context_links (passage_id, related_passage_id, relation_type, priority) VALUES (?,?,?,?)",
        rows,
    )


def set_info(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO corpus_info (key, value) VALUES (?, ?)", (key, value))
