"""Context by source type: Quran = window of neighbouring ayat; hadith = the full hadith only."""

import pytest

from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus


def test_hadith_context_is_the_single_full_hadith(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    full = real_repo.get("hadith:bukhari:7563")
    r = ask(p, " ".join(full.normalized_text.split()[-14:]), "ادعاء")
    ctx = r.context
    assert ctx.before == [] and ctx.after == [] and len(ctx.matched) == 1
    u = ctx.matched[0]
    assert u.text == full.original_text and u.source_type == "hadith"
    m = u.metadata
    assert m["collection_ar"] == "صحيح البخاري" and m["hadith_number"] == "7563"
    assert m["book"] and m["chapter"] and m["grading_authority"] == "SCIENTIFIC_PACKAGE_SAHIHAYN_RULE"
    roles = [e.role for e in r.evidence.items]
    assert roles == ["matched_source", "metadata"]       # no adjacent hadith as context


def test_quran_context_unchanged(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, real_repo.get("quran:2:255").metadata["publisher_aya_text_emlaey"], "ادعاء")
    assert [u.passage_id for u in r.context.before] == ["quran:2:253", "quran:2:254"]
    assert [u.passage_id for u in r.context.after] == ["quran:2:256", "quran:2:257"]
    assert all(u.source_type == "quran" for u in r.context.before + r.context.matched + r.context.after)
