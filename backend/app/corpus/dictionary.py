"""Ingest terminology entries (source_type 'dictionary') into the `terms` table.

Terms are NOT passages: they are never indexed for quote matching and never attributed as the
source of a quote. They are looked up by exact normalized term (services/terminology.py).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.corpus.common import SourceRecord, insert_source
from app.services.normalizer import normalize_for_search


def ingest(conn: sqlite3.Connection, path: Path, corpus_version: str) -> int:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sid = doc["source_id"]
    insert_source(conn, SourceRecord(
        id=sid, source_type="dictionary", title=doc["title"], edition=doc["edition"],
        publisher=doc["publisher"], source_url=None, license_note=doc["license_note"],
        verification_status=doc["status"], acquired_at=doc["acquired_at"], corpus_version=corpus_version,
        metadata={"provenance": doc["reference"] + f" (package sha256 {doc['package_file']['sha256']})",
                  "records": doc.get("records"), "scope_note": doc.get("scope_note"),
                  "extraction": doc["extraction"]["correction_rule"]},
    ))
    for e in doc["entries"]:
        conn.execute(
            "INSERT INTO terms (id, source_id, term_ar, term_normalized, language, translation, usage_note, "
            "reference, metadata_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (e["id"], sid, e["term_ar"], normalize_for_search(e["term_ar"]), e["language"], e["translation"],
             e["usage_note_ar"], doc["reference"], json.dumps({"text_layer": e["text_layer"]}, ensure_ascii=False)))
    return len(doc["entries"])
