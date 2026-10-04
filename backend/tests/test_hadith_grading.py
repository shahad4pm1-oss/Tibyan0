"""Hadith grading: recorded from the official package rule, never generated, never by a model."""

import json
import shutil

import pytest

from app.corpus.validation import validate
from app.db.connection import connect
from app.schemas.claim_analysis import LLMClaimOutput
from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus


def test_every_hadith_has_package_grading_not_model(real_repo):
    rows = real_repo.conn.execute("SELECT id, metadata_json FROM passages WHERE source_id LIKE 'hadith:%'")
    n = 0
    for pid, mj in rows:
        m = json.loads(mj)
        assert m["grading_authority"] == "SCIENTIFIC_PACKAGE_SAHIHAYN_RULE", pid
        assert m["grading_generated_by_model"] is False, pid
        assert m["grading"] == "SAHIHAYN" and m["grading_source"].startswith("Scientific Package p.3")
        n += 1
    assert n == 10494


def test_llm_output_schema_has_no_grading_field():
    assert not any("grad" in f for f in LLMClaimOutput.model_fields)


@pytest.mark.parametrize("patch", [
    {"grading_authority": "LLM"},
    {"grading_generated_by_model": True},
    {"grading": None},
])
def test_validation_rejects_bad_grading(real_db, tmp_path, patch):
    dst = tmp_path / "c.sqlite3"
    shutil.copy(real_db, dst)
    c = connect(dst)
    m = json.loads(c.execute("SELECT metadata_json FROM passages WHERE id='hadith:bukhari:1'").fetchone()[0])
    m.update(patch)
    c.execute("UPDATE passages SET metadata_json=? WHERE id='hadith:bukhari:1'", (json.dumps(m, ensure_ascii=False),))
    c.commit()
    rep = validate(c, production=True)
    assert not rep.ok and any(e.startswith(("V15", "V07")) for e in rep.errors)


def test_hadith_is_never_sent_to_the_model(real_db, real_repo):
    """A resolved hadith with a scripted model: the model is not called and no verdict is produced."""
    quote = " ".join(real_repo.get("hadith:bukhari:1").normalized_text.split()[-12:])
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, quote, "هذا الحديث يدل على أن النية شرط")
    assert r.source and r.source.source_type == "hadith"
    ca = r.claim_analysis
    assert ca.attempts == 0 and ca.summary_source == "system_template" and ca.relation is None
    assert ca.status == "ANALYSIS_UNAVAILABLE" and "CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE" in ca.gate.reasons
    assert p.llm.calls == []
