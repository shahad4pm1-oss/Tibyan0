"""LLM evidence_ids ⊆ backend evidence_ids; no external sources or references."""

import pytest

from app.schemas.claim_analysis import LLMClaimOutput
from app.services.citation_verifier import verify
from app.services.evidence_builder import Evidence

from .conftest import good_output

EV = [
    Evidence("E1", "quran:2:191", "quran", "2:191", "t", "matched_source",
             metadata={"surah_number": 2, "ayah_number": 191, "surah_name": "البَقَرَة"}),
    Evidence("E2", "quran:2:190", "quran", "2:190", "t", "preceding_context",
             metadata={"surah_number": 2, "ayah_number": 190, "surah_name": "البَقَرَة"}),
    Evidence("E3", None, "quran", None, "meta", "metadata", metadata={}),
]


def v(**over):
    return verify(LLMClaimOutput.model_validate(good_output(**over)), EV)


def test_valid_citation_passes():
    assert v(ids=("E1",)) == []
    assert v(ids=("E2",), reason="E2 في سورة البقرة، الآية 190 (2:190) يقيد المعنى.") == []


def test_nonexistent_id_rejected():
    assert "UNKNOWN_EVIDENCE_ID" in v(ids=("E7",))


def test_key_evidence_id_must_exist():
    o = good_output()
    o["evidence_ids"] = ["E1", "E8"]
    o["key_evidence"] = [{"evidence_id": "E8", "relevance": "x"}]
    assert "UNKNOWN_EVIDENCE_ID" in verify(LLMClaimOutput.model_validate(o), EV)


def test_metadata_only_citation_not_enough_for_verdict():
    assert "NO_SUBSTANTIVE_EVIDENCE_CITED" in v(ids=("E3",))


@pytest.mark.parametrize("text", [
    "E1 يتفق مع ما في 4:58.",
    "E1 وهو ما تذكره الآية 75 أيضا.",
    "E1 ويشبهه ما في سورة النساء.",
    "E1 ٥:٣٢ يؤكد هذا.",
])
def test_unsupplied_reference_rejected(text):
    assert "EXTERNAL_REFERENCE" in v(reason=text)


@pytest.mark.parametrize("text", [
    "E1 وقد رواه البخاري.", "ذكر ابن كثير في تفسيره أن E1 مقيد.", "قال العلماء إن E1 عام.",
    "E1 وفي الحديث ما يؤيده.", "As in Sahih Bukhari, E1.", "E1 وفق فتوى معروفة.", "وبالتفسير المشهور E1.",
])
def test_unsupplied_source_mentions_rejected(text):
    assert "UNSUPPORTED_SOURCE_MENTION" in v(reason=text)


def test_checks_cover_all_free_text_fields():
    o = good_output()
    o["key_evidence"] = [{"evidence_id": "E1", "relevance": "رواه مسلم"}]
    assert "UNSUPPORTED_SOURCE_MENTION" in verify(LLMClaimOutput.model_validate(o), EV)
    o = good_output(relation="INSUFFICIENT_EVIDENCE", uncertainty_reason="ينبغي مراجعة تفسير الطبري")
    assert "UNSUPPORTED_SOURCE_MENTION" in verify(LLMClaimOutput.model_validate(o), EV)
