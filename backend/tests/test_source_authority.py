"""Source authority: only APPROVED sources are indexed or served; every evidence item names its source type."""

import shutil

import pytest

from app.corpus.common import PassageRecord, SourceRecord, insert_passages, insert_source
from app.corpus.fts import build_fts
from app.corpus.validation import validate
from app.db.connection import connect
from app.repositories.corpus import CorpusRepository
from app.services.normalizer import normalize_for_search
from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus
TEXT = "جملة اختبار غير دينية عن القطار السريع والمحطة الجديدة"


def _add(c, sid, stype, status):
    insert_source(c, SourceRecord(id=sid, source_type=stype, title=sid, edition="t", license_note="test",
                                  verification_status=status, acquired_at="2026-10-02", corpus_version="t",
                                  source_url="https://example.invalid/" + sid))
    insert_passages(c, [PassageRecord(id=f"{sid}:1", source_id=sid, reference="1", sequence=1, parent_id=None,
                                      original_text=TEXT, normalized_text=normalize_for_search(TEXT),
                                      metadata={"collection": sid, "hadith_number": "1", "grading": "x",
                                                "grading_source": "x"})])


@pytest.mark.parametrize("status", ["PENDING_REVIEW", "REJECTED"])
def test_pending_or_rejected_source_never_indexed_or_served(real_db, tmp_path, status):
    dst = tmp_path / "c.sqlite3"
    shutil.copy(real_db, dst)
    c = connect(dst)
    _add(c, "hadith:test", "hadith", status)
    build_fts(c, production=True)
    c.commit()
    hrepo = CorpusRepository(c, "hadith_fts")
    assert hrepo.phrase_hits(normalize_for_search(TEXT).split()) == []
    assert hrepo.get("hadith:test:1") is None
    rep = validate(c, production=True)
    assert any(e.startswith("V01") for e in rep.errors)


def test_unindexed_source_types_never_enter_quran_or_hadith_index(real_db, tmp_path):
    """e.g. a tafsir source (none is ingested): even if APPROVED it is not searchable as Quran or hadith."""
    dst = tmp_path / "c.sqlite3"
    shutil.copy(real_db, dst)
    c = connect(dst)
    _add(c, "tafsir:test", "tafsir", "APPROVED")
    build_fts(c, production=True)
    c.commit()
    for ix in ("passages_fts", "hadith_fts"):
        assert CorpusRepository(c, ix).phrase_hits(normalize_for_search(TEXT).split()) == []


def test_evidence_items_carry_source_type_and_status(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    words = real_repo.get("hadith:muslim:1907").normalized_text.split()[-12:]
    r = ask(p, " ".join(words), "ادعاء")
    assert r.source.source_type == "hadith"
    for e in r.evidence.items:
        assert e.source_type == "hadith" and e.verification_status == "APPROVED"
        assert e.source_id == "hadith:muslim"
    q = ask(p, real_repo.get("quran:112:1").metadata["publisher_aya_text_emlaey"], "ادعاء")
    assert {e.source_type for e in q.evidence.items} == {"quran"}
