"""Scripted model outputs that try to invent material. Every one must be rejected (after the single retry)
and the result must abstain. Real-corpus text is read from the DB; nothing religious is typed here."""

import pytest

from .conftest import ask, good_output, make_pipeline

CLAIM = "الآية تأمر بقتل غير المسلمين مطلقا"


def other_ayah(repo, pid="quran:9:5", n=8):
    return " ".join(repo.get(pid).metadata["publisher_aya_text_emlaey"].split()[:n])


CASES = {
    "another_ayah": lambda r: good_output("OVERSTATED", reason="E1 ويؤيده " + other_ayah(r)),
    "another_ayah_quoted": lambda r: good_output("OVERSTATED", reason="E1 وانظر «" + other_ayah(r) + "»"),
    "invented_tafsir": lambda r: good_output("OVERSTATED", reason="ذكر الطبري في تفسيره أن E1 مقيد."),
    "invented_scholar": lambda r: good_output("OVERSTATED", reason="قال ابن تيمية إن E1 خاص بالمحاربين."),
    "invented_hadith_source": lambda r: good_output("OVERSTATED", reason="E1 وقد رواه البخاري في صحيحه."),
    "nonexistent_evidence": lambda r: good_output("OVERSTATED", ids=("E1", "E12")),
    "unsupplied_reference": lambda r: good_output("OVERSTATED", reason="E1 كما في 8:61 من سورة الأنفال."),
    "model_memory_consensus": lambda r: good_output("CONTRADICTED", reason="أجمع العلماء على خلاف ذلك، انظر E1."),
    "scripture_formatted": lambda r: good_output("OVERSTATED", summary=r.get("quran:9:5").original_text[:40]),
}


@pytest.mark.real_corpus
@pytest.mark.parametrize("name", list(CASES))
def test_invented_material_rejected(real_db, real_repo, real_quote, name):
    out = CASES[name](real_repo)
    p = make_pipeline(real_db, [out, out], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, real_quote, CLAIM)
    ca = r.claim_analysis
    assert ca.status == "AI_OUTPUT_REJECTED", (name, ca)
    assert ca.relation == "INSUFFICIENT_EVIDENCE" and ca.summary_source == "system_template"
    assert ca.attempts == 2
    # verified source material is still shown
    assert r.source.reference == "2:191" and [u.passage_id for u in r.context.matched] == ["quran:2:191"]


@pytest.mark.real_corpus
def test_valid_grounded_output_accepted(real_db, real_quote):
    ok = good_output("OVERSTATED", ids=("E1", "E3", "E4"),
                     reason="E3 يقيّد القتال بمن يقاتل، وE4 يذكر الانتهاء، فالادعاء أوسع مما يدل عليه E1 في سياقه.")
    p = make_pipeline(real_db, [ok], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, real_quote, CLAIM)
    assert r.claim_analysis.status == "COMPLETED" and r.claim_analysis.relation == "OVERSTATED"
    assert r.claim_analysis.summary_source == "ai"
