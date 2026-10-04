"""Hadith importer, exercised ONLY with synthetic non-religious fixtures."""

import json

import pytest

from app.corpus.hadith import HadithIngestError, ingest
from app.db.connection import connect, init_schema

from .conftest import FIX


def test_imported_fields(synthetic_repo):
    h = synthetic_repo.get("synth_collection:1")
    for k in ("collection", "hadith_number", "book", "book_number", "chapter", "grading", "grading_source"):
        assert h.metadata.get(k) not in (None, "")
    assert synthetic_repo.source("synth_collection")["source_type"] == "synthetic_fixture"


def _db(tmp_path):
    c = connect(tmp_path / "h.sqlite3")
    init_schema(c)
    return c


def test_missing_grading_rejected(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"number": "1", "text": "نص تجريبي", "grading": "", "grading_source": "x"}))
    with pytest.raises(HadithIngestError):
        ingest(_db(tmp_path), FIX / "synthetic_hadith_manifest.json", bad, "t")


def test_duplicate_number_rejected(tmp_path):
    bad = tmp_path / "dup.jsonl"
    row = json.dumps({"number": "1", "text": "نص تجريبي", "grading": "SYNTHETIC", "grading_source": "x"})
    bad.write_text(row + "\n" + row)
    with pytest.raises(HadithIngestError):
        ingest(_db(tmp_path), FIX / "synthetic_hadith_manifest.json", bad, "t")


def test_no_neighbour_links_for_hadith(synthetic_repo):
    n = synthetic_repo.conn.execute(
        "SELECT count(*) FROM context_links WHERE passage_id LIKE 'synth_collection:%'").fetchone()[0]
    assert n == 0
