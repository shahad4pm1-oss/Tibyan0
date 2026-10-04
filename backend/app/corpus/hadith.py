"""Hadith ingestion from Tibyan's canonical hadith JSONL format.

No real Bukhari/Muslim dataset with cleared provenance is available yet
(REAL_HADITH = BLOCKED_BY_DATA). This importer is exercised only with synthetic
NON-RELIGIOUS fixtures. A future adapter converts a real, approved edition into
this format; nothing here invents hadith text.

Manifest (JSON) fields: source_id, collection, title, author, edition, publisher,
source_url, license_note, verification_status, acquired_at, grading_rule, source_type.

JSONL record fields (one per hadith):
  number (str|int, required)   book (str)   book_number (int)
  chapter (str)                chapter_number (int)
  text (str, required)         grading (str, required)   grading_source (str, required)
  extra (object, optional)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.corpus.common import PassageRecord, SourceRecord, insert_passages, insert_source
from app.services.normalizer import normalize_for_search, normalize_hadith_search

REQUIRED = ("number", "text", "grading", "grading_source")


class HadithIngestError(RuntimeError):
    pass


def ingest(conn: sqlite3.Connection, manifest_path: Path, jsonl_path: Path, corpus_version: str) -> int:
    man = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sid = man["source_id"]
    insert_source(conn, SourceRecord(
        id=sid,
        source_type=man.get("source_type", "hadith"),
        title=man["title"],
        author=man.get("author"),
        edition=man["edition"],
        publisher=man.get("publisher"),
        source_url=man.get("source_url"),
        license_note=man["license_note"],
        verification_status=man["verification_status"],
        acquired_at=man["acquired_at"],
        corpus_version=corpus_version,
        metadata={"collection": man["collection"], "grading_rule": man.get("grading_rule")},
    ))

    passages: list[PassageRecord] = []
    seen: set[str] = set()
    for line_no, line in enumerate(Path(jsonl_path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        rec = json.loads(line)
        missing = [k for k in REQUIRED if not str(rec.get(k, "")).strip()]
        if missing:
            raise HadithIngestError(f"line {line_no}: missing {missing}")
        num = str(rec["number"])
        pid = f"{sid}:{num}"
        if pid in seen:
            raise HadithIngestError(f"line {line_no}: duplicate number {num}")
        seen.add(pid)
        book_no = rec.get("book_number")
        passages.append(PassageRecord(
            id=pid,
            source_id=sid,
            reference=num,
            sequence=len(passages) + 1,
            parent_id=f"{sid}:book:{book_no}" if book_no is not None else None,
            original_text=rec["text"],
            normalized_text=normalize_hadith_search(rec["text"]),
            normalized_text_alt=normalize_for_search(rec["text"]),
            metadata={
                "collection": man["collection"],
                "hadith_number": num,
                "book": rec.get("book"),
                "book_number": book_no,
                "chapter": rec.get("chapter"),
                "chapter_number": rec.get("chapter_number"),
                "grading": rec["grading"],
                "grading_source": rec["grading_source"],
                "extra": rec.get("extra", {}),
            },
        ))
    insert_passages(conn, passages)
    # Deliberately no previous/next links: adjacent hadith are not interpretive context.
    return len(passages)
