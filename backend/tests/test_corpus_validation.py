"""Validation must pass on the real corpus and FAIL on corrupted copies."""

import json

import pytest

from app.corpus.common import SourceRecord, insert_source, set_info
from app.corpus.validation import validate
from app.db.connection import connect

ROOT_META = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "metadata"
EXPECTED = ROOT_META / "quran_structure_expected.json"


def run(db, production=True):
    return validate(connect(db), production=production, structure_expected=EXPECTED)


def codes(rep):
    return {e.split(":")[0] for e in rep.errors}


def test_synthetic_corpus_valid_in_test_mode(synthetic_db):
    rep = validate(connect(synthetic_db), production=False)
    assert rep.ok, rep.errors


def test_synthetic_corpus_rejected_as_production(synthetic_db):
    rep = validate(connect(synthetic_db), production=True)
    assert "V01" in codes(rep)


@pytest.mark.real_corpus
def test_real_corpus_valid(real_db):
    rep = run(real_db)
    assert rep.ok, rep.errors
    assert {"V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08", "V09", "V10", "V11", "V12", "V13"} \
        <= set(rep.checks_run)


@pytest.mark.real_corpus
def test_altered_original_text_fails(real_copy):
    c = connect(real_copy)
    c.execute("UPDATE passages SET original_text = original_text || 'x' WHERE id = 'quran:2:255'")
    c.commit()
    assert {"V12", "V13", "V06"} <= codes(run(real_copy))


@pytest.mark.real_corpus
def test_missing_passage_fails(real_copy):
    c = connect(real_copy)
    c.execute("DELETE FROM passages WHERE id = 'quran:3:7'")
    c.execute("DELETE FROM passages_fts WHERE rowid NOT IN (SELECT rowid_int FROM passages)")
    c.commit()
    assert {"V08", "V11"} <= codes(run(real_copy))


@pytest.mark.real_corpus
def test_stale_normalized_text_fails(real_copy):
    c = connect(real_copy)
    c.execute("UPDATE passages SET normalized_text = 'نص' WHERE id = 'quran:1:2'")
    c.commit()
    assert "V06" in codes(run(real_copy))


@pytest.mark.real_corpus
def test_pending_source_in_production_fails(real_copy):
    c = connect(real_copy)
    insert_source(c, SourceRecord(id="extra", source_type="hadith", title="t", edition="e", license_note="l",
                                  verification_status="PENDING_REVIEW", acquired_at="d", corpus_version="v"))
    c.commit()
    assert "V01" in codes(run(real_copy))


@pytest.mark.real_corpus
def test_ineligible_row_in_index_fails(real_copy):
    c = connect(real_copy)
    c.execute("UPDATE sources SET verification_status = 'REJECTED' WHERE id = 'quran'")
    c.commit()
    assert {"V01", "V10"} <= codes(run(real_copy))


@pytest.mark.real_corpus
def test_broken_context_link_fails(real_copy):
    c = connect(real_copy)
    c.execute("INSERT INTO context_links (passage_id, related_passage_id, relation_type) "
              "VALUES ('quran:1:7', 'quran:2:1', 'next')")  # crosses surah boundary
    c.commit()
    assert "V09" in codes(run(real_copy))


@pytest.mark.real_corpus
def test_wrong_corpus_kind_fails(real_copy):
    c = connect(real_copy)
    set_info(c, "corpus_kind", "test_fixture")
    c.commit()
    assert "V01" in codes(run(real_copy))


@pytest.mark.real_corpus
def test_metadata_missing_fails(real_copy):
    c = connect(real_copy)
    meta = json.loads(c.execute("SELECT metadata_json FROM passages WHERE id='quran:4:1'").fetchone()[0])
    del meta["surah_name"]
    c.execute("UPDATE passages SET metadata_json = ? WHERE id='quran:4:1'", (json.dumps(meta, ensure_ascii=False),))
    c.commit()
    assert "V07" in codes(run(real_copy))
