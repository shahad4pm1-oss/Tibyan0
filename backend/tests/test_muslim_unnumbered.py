"""Sahih Muslim narrations that the source file does not number: kept with an INTERNAL id and a
book/chapter locator, hadith_number = null. No number is ever invented."""

import json

import pytest

from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus


def test_unnumbered_records_have_locator_and_no_number(real_repo):
    rows = real_repo.conn.execute(
        "SELECT id, reference, metadata_json FROM passages WHERE id LIKE 'hadith:muslim:u:%'").fetchall()
    assert len(rows) == 192
    for pid, ref, mj in rows:
        m = json.loads(mj)
        assert m["hadith_number"] is None
        loc = m["locator"]
        assert pid == f"hadith:muslim:u:{loc['book_number']}:{loc['chapter_number']}:{loc['unnumbered_ordinal_in_chapter']}"
        assert m["book"] and m["chapter"].startswith("باب") and ref.startswith("u:")
        assert "غير مرقّمة" in m["grading_ar"]
    # numbers 1-99 are still absent: nothing was numbered by inference
    nums = {json.loads(r[0])["hadith_number"] for r in real_repo.conn.execute(
        "SELECT metadata_json FROM passages WHERE source_id='hadith:muslim'")}
    assert not any(str(n) in nums for n in range(1, 100))


def test_unnumbered_narration_text_is_findable_and_cited_by_book_and_chapter(real_db, real_repo):
    first = real_repo.get("hadith:muslim:u:1:1:1")
    assert first.metadata["book"] == "كتاب الإيمان" and first.metadata["chapter"].startswith("باب معرفة الإيمان")
    assert not first.original_text[:1].isdigit()                      # edition digit markers are removed
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    words = first.original_text.split()
    k = words.index("بينما") if "بينما" in words else 40
    r = ask(p, " ".join(words[k:k + 12]), "ادعاء")
    ids = {u.passage_id for u in r.context.matched} | {a.passage_id for a in r.quote_analysis.alternatives}
    assert "hadith:muslim:u:1:1:1" in ids
    u = next(x for x in (r.context.matched + r.quote_analysis.alternatives) if x.passage_id == "hadith:muslim:u:1:1:1")
    assert u.metadata.get("hadith_number") is None and u.metadata["locator"]["chapter_number"] == 1
