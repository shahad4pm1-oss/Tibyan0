"""Quran ingestion: KFGQPC hafsData CSV -> canonical passages.

Transforms are documented in data/metadata/quran_kfgqpc_hafs_v2.json.
No text is generated or edited beyond removing the trailing ayah-number glyph,
which is reversible and proven by validation.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path

from app.corpus.common import (
    PassageRecord,
    SourceRecord,
    insert_passages,
    insert_source,
    link_sequential,
    sha256_file,
)
from app.services.normalizer import normalize_for_search

# Trailing separator (NBSP, or plain space as in 2:286) + one ayah-number glyph.
# Glyphs observed are in Arabic Presentation Forms / PUA ranges, never Arabic letters U+0600-U+06FF.
_TRAILING_MARK = re.compile("([  ])([-ﭐ-﷿ﹰ-﻿])$")

REQUIRED_COLUMNS = {"id", "jozz", "page", "sura_no", "sura_name_en", "sura_name_ar",
                    "line_start", "line_end", "aya_no", "aya_text", "aya_text_emlaey"}


class IngestError(RuntimeError):
    pass


def split_publisher_text(aya_text: str) -> tuple[str, str, str]:
    """Return (original_text, separator, mark). Raises if the publisher format is not as expected."""
    m = _TRAILING_MARK.search(aya_text)
    if not m:
        raise IngestError("aya_text does not end with separator + ayah-number glyph")
    return aya_text[: m.start()], m.group(1), m.group(2)


def read_rows(zip_path: Path, member: str) -> list[dict]:
    with zipfile.ZipFile(zip_path) as z:
        raw = z.read(member).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows or not REQUIRED_COLUMNS.issubset(rows[0].keys()):
        raise IngestError(f"unexpected columns: {list(rows[0].keys()) if rows else 'no rows'}")
    return rows


def ingest(conn: sqlite3.Connection, meta_path: Path, repo_root: Path, corpus_version: str) -> int:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pkg = meta["package"]
    zip_path = repo_root / pkg["local_path"]
    if not zip_path.exists():
        raise IngestError(f"raw package missing: {zip_path} (run scripts/fetch_quran.py)")
    digest = sha256_file(zip_path)
    if digest != pkg["sha256"]:
        raise IngestError(f"sha256 mismatch: {digest} != {pkg['sha256']}")

    rows = read_rows(zip_path, pkg["member_used"])

    insert_source(conn, SourceRecord(
        id=meta["source_id"],
        source_type="quran",
        title="القرآن الكريم — مصحف المدينة النبوية (رواية حفص عن عاصم)",
        author=None,
        edition=meta["edition"],
        publisher=meta["publisher"],
        source_url=pkg["official_url"],
        license_note=meta["license_or_terms"]["summary"],
        verification_status=meta["status"],
        acquired_at=meta["acquisition"]["acquired_at"],
        corpus_version=corpus_version,
        metadata={"dataset_id": meta["dataset_id"], "package_sha256": digest,
                  "member": pkg["member_used"], "riwayah": meta["riwayah"]},
    ))

    passages: list[PassageRecord] = []
    by_surah: dict[str, list[str]] = {}
    for seq, r in enumerate(rows, start=1):
        s, a = int(r["sura_no"]), int(r["aya_no"])
        original, sep, mark = split_publisher_text(r["aya_text"])
        pid = f"quran:{s}:{a}"
        passages.append(PassageRecord(
            id=pid,
            source_id=meta["source_id"],
            reference=f"{s}:{a}",
            sequence=seq,
            parent_id=f"quran:{s}",
            original_text=original,
            normalized_text=normalize_for_search(r["aya_text_emlaey"]),
            normalized_text_alt=normalize_for_search(original),
            metadata={
                "surah_number": s,
                "ayah_number": a,
                "surah_name": r["sura_name_ar"],
                "surah_name_en": r["sura_name_en"],
                "juz": int(r["jozz"]),
                "page": int(r["page"]),
                "line_start": int(r["line_start"]),
                "line_end": int(r["line_end"]),
                "publisher_row_id": int(r["id"]),
                "publisher_aya_text": r["aya_text"],
                "publisher_aya_text_emlaey": r["aya_text_emlaey"],
                "trailing_separator": sep,
                "ayah_mark_glyph": mark,
            },
        ))
        by_surah.setdefault(f"quran:{s}", []).append(pid)

    insert_passages(conn, passages)
    link_sequential(conn, by_surah)
    return len(passages)
