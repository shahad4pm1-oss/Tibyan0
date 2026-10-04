"""Deterministic quote comparison (app/services/text_diff.py) on the real corpus.

Quran quotes are read from the database (publisher's imla'i text) and mutated programmatically; nothing is typed
from memory. Normalization-only differences must never be reported as missing, added or substituted words, and
the canonical text must come back exactly as stored.
"""

import unicodedata

import pytest

from app.services import text_diff
from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus

SUBSTANTIVE = {"SUBSTITUTED_WORDS", "MISSING_WORDS", "ADDED_WORDS"}


@pytest.fixture(scope="module")
def pipe(real_db):
    return make_pipeline(real_db, provider=None, embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")


def imla(repo, pid):
    return repo.get(pid).metadata["publisher_aya_text_emlaey"]


def codes(c):
    return {s.code if hasattr(s, "code") else s["code"] for s in c.summary} if hasattr(c, "summary") else \
        {s["code"] for s in c["summary"]}


def canonical_display_is_stored(c, repo):
    """The canonical side is the stored text, token for token (never normalized)."""
    toks = c.canonical_tokens if hasattr(c, "canonical_tokens") else c["canonical_tokens"]
    ids = c.passage_ids if hasattr(c, "passage_ids") else c["passage_ids"]
    stored = " ".join(repo.get(i).original_text for i in ids).split()
    return [t.text if hasattr(t, "text") else t["text"] for t in toks] == stored


def test_exact_quran_is_verbatim_and_definitive(pipe, real_repo):
    r = ask(pipe, imla(real_repo, "quran:1:2"), "ادعاء")
    c = r.quote_comparison
    assert r.quote_analysis.match_status == "EXACT" and c.definitive and c.basis == "imlaei"
    assert codes(c) == {"VERBATIM"}
    assert all(t.status == "MATCHED" for t in c.canonical_tokens)
    assert canonical_display_is_stored(c, real_repo)
    assert r.candidate_comparisons == []


def test_quran_with_added_diacritics_is_normalization_only(pipe, real_repo):
    q = " ".join(w[0] + "َ" + w[1:] for w in imla(real_repo, "quran:1:2").split())   # a fatha on each word
    r = ask(pipe, q, "ادعاء")
    c = r.quote_comparison
    assert r.quote_analysis.match_status == "EXACT"
    assert codes(c) == {"NORMALIZATION_ONLY"} and c.summary[0].reasons == ["diacritics"]
    assert not codes(c) & SUBSTANTIVE


def test_quran_with_punctuation_and_brackets_is_normalization_only(pipe, real_repo):
    w = imla(real_repo, "quran:1:2").split()
    q = "«" + w[0] + " " + w[1] + "، " + " ".join(w[2:]) + "» (" + "٢" + ")"
    r = ask(pipe, q, "ادعاء")
    c = r.quote_comparison
    assert r.quote_analysis.match_status == "EXACT"
    assert codes(c) == {"NORMALIZATION_ONLY"} and "punctuation" in c.summary[0].reasons
    assert all(t.status in ("MATCHED", "NORMALIZATION_ONLY", "IGNORED") for t in c.user_tokens)


def test_uthmani_paste_compares_against_the_canonical_column(pipe, real_repo):
    r = ask(pipe, real_repo.get("quran:1:2").original_text, "ادعاء")
    c = r.quote_comparison
    assert c.basis == "canonical" and codes(c) == {"VERBATIM"}


def test_partial_verse_marks_the_rest_as_outside_the_quote(pipe, real_repo, real_quote):
    r = ask(pipe, real_quote, "ادعاء")
    c = r.quote_comparison
    assert r.quote_analysis.match_status == "PARTIAL" and c.definitive
    assert "PARTIAL_QUOTE" in codes(c) and not codes(c) & SUBSTANTIVE
    st = [t.status for t in c.canonical_tokens]
    assert st[:4] == ["MATCHED"] * 4 and set(st[4:]) == {"OUTSIDE_QUOTE"}
    assert c.quoted_range == [0, 3]
    assert canonical_display_is_stored(c, real_repo)


def test_one_missing_word_is_a_non_definitive_candidate_comparison(pipe, real_repo):
    w = imla(real_repo, "quran:2:191").split()[:8]
    q = " ".join(w[:3] + w[4:])                       # drop the 4th word
    r = ask(pipe, q, "ادعاء")
    assert r.quote_analysis.ambiguity_reason == "NEAR_MATCH_UNCONFIRMED"
    assert r.quote_comparison is None                 # no definitive diff without a resolved source
    top = r.candidate_comparisons[0]
    assert top.definitive is False and top.passage_ids == ["quran:2:191"]
    assert "MISSING_WORDS" in codes(top)
    missing = [d for d in top.differences if d.kind == "DELETED_FROM_USER_QUOTE"]
    assert len(missing) == 1


def test_one_substituted_word(pipe, real_repo):
    w = imla(real_repo, "quran:2:191").split()[:8]
    other = imla(real_repo, "quran:1:2").split()[-1]   # a real word from elsewhere
    q = " ".join(w[:4] + [other] + w[5:])
    r = ask(pipe, q, "ادعاء")
    top = r.candidate_comparisons[0]
    assert top.passage_ids == ["quran:2:191"] and "SUBSTITUTED_WORDS" in codes(top)
    sub = [d for d in top.differences if d.kind == "SUBSTITUTED"]
    assert sub[0].user == other and sub[0].canonical == w[5 - 1]


def test_one_additional_word(pipe, real_repo):
    w = imla(real_repo, "quran:2:191").split()[:8]
    extra = imla(real_repo, "quran:1:2").split()[0]
    q = " ".join(w[:4] + [extra] + w[4:])
    r = ask(pipe, q, "ادعاء")
    top = r.candidate_comparisons[0]
    assert "ADDED_WORDS" in codes(top)
    assert [t.text for t in top.user_tokens if t.status == "ADDED_BY_USER"] == [extra]


@pytest.mark.parametrize("quote,reason", [
    ("سمعت رسول الله ﷺ يقول: «إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى»", "honorific"),
    ("سمعت رسول الله يقول إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "honorific"),
])
def test_hadith_honorific_variation_is_normalization_only(pipe, real_repo, quote, reason):
    r = ask(pipe, quote, "ادعاء")
    c = r.quote_comparison
    assert r.source.source_type == "hadith" and c.definitive and c.basis == "canonical"
    assert not codes(c) & SUBSTANTIVE
    reasons = {x for s in c.summary for x in s.reasons}
    assert reason in reasons
    assert canonical_display_is_stored(c, real_repo)


def test_partial_hadith(pipe):
    r = ask(pipe, "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "ادعاء")
    c = r.quote_comparison
    assert r.quote_analysis.match_status == "PARTIAL" and "PARTIAL_QUOTE" in codes(c)
    assert not codes(c) & SUBSTANTIVE
    assert {t.status for t in c.canonical_tokens[: c.quoted_range[0]]} == {"OUTSIDE_QUOTE"}


def test_arabic_presentation_forms_are_normalization_only(pipe):
    q = unicodedata.normalize("NFC", "سمعت رسول الله ﷺ يقول إنما الأعمال بالنيات")
    pres = q.replace("قال", "ﻗﺎﻝ").replace("إنما", "ﺇﻧﻤﺎ")
    r = ask(pipe, pres, "ادعاء")
    c = r.quote_comparison
    assert c is not None and not codes(c) & SUBSTANTIVE
    assert "presentation_forms" in {x for s in c.summary for x in s.reasons}


@pytest.mark.parametrize("quote", ["إنما الأعمال بالنية", "حدثنا قتيبة بن سعيد"])   # verbatim in several hadith
def test_ambiguous_hadith_candidates_get_no_definitive_or_candidate_diff(pipe, quote):
    r = ask(pipe, quote, "ادعاء")
    assert r.quote_analysis.match_status == "AMBIGUOUS"
    assert {a.source_type for a in r.quote_analysis.alternatives} == {"hadith"}
    assert r.quote_analysis.ambiguity_reason == "MULTIPLE_LOCATIONS"
    assert r.quote_comparison is None and r.candidate_comparisons == []


def test_not_found_gives_no_comparison(pipe):
    r = ask(pipe, "هذا نص عربي عادي لا يوجد في المصادر المعتمدة اطلاقا", "ادعاء")
    assert r.quote_analysis.match_status == "NOT_FOUND"
    assert r.quote_comparison is None and r.candidate_comparisons == []


def test_comparison_never_changes_existing_fields(pipe, real_repo, real_quote):
    """The comparison is additive: matching, source, context and evidence are exactly the pipeline's."""
    r = ask(pipe, real_quote, "ادعاء")
    assert [u.text for u in r.context.matched] == [real_repo.get("quran:2:191").original_text]
    assert r.evidence.items[0].text == real_repo.get("quran:2:191").original_text


# ---- module-level checks (no pipeline)

def test_reasons_are_specific():
    assert text_diff.norm_reasons("أشد", "اشد") == ["alef_forms"]
    assert text_diff.norm_reasons("الـله", "الله") == ["tatweel"]
    assert text_diff.norm_reasons("قال:", "قال") == ["punctuation"]
    assert text_diff.norm_reasons("ﻗﺎﻝ", "قال") == ["presentation_forms"]
    assert text_diff.norm_reasons("قال", "قال") == []


def test_user_tokens_keep_their_written_form(real_repo):
    q = "«الحمدُ لله»"
    c = text_diff.compare(q, [real_repo.get("quran:1:2")], "quran", True)
    assert [t["text"] for t in c["user_tokens"]] == q.split()
