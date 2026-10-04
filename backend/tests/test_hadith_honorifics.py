"""Hadith search normalization (hnorm-v1): honorifics, presentation forms, diacritics, punctuation.

Search-only: the stored and displayed text never changes.
"""

import pytest

from app.services.normalizer import hadith_tokens, normalize_for_search, normalize_hadith_search
from tests.conftest import ask, make_pipeline

BASE = "قال رسول الله يقول انما الاعمال بالنيات"


@pytest.mark.parametrize("variant", [
    "قال رسول الله ﷺ يقول: «إنما الأعمال بالنيات»",              # symbol
    "قال رسول الله صلى الله عليه وسلم يقول إنما الأعمال بالنيات",  # written out
    "قال رسولُ اللهِ صلّى اللهُ عليهِ وسلَّمَ يقولُ: إنّما الأعمالُ بالنّيّات",  # diacritics
    "قال رسول الله يقول إنما الأعمال بالنيات",                    # omitted
    "قال رسول الله (صلى الله عليه وآله وسلم) يقول، «إنما» الأعمال... بالنيات!",  # punctuation, variant
    "قال رسول الـله ﷺ يقـول إنما الأعمال بالنيـات",               # tatweel
])
def test_variants_normalize_to_the_same_search_text(variant):
    assert normalize_hadith_search(variant) == BASE


def test_companion_honorifics_and_presentation_forms():
    assert normalize_hadith_search("عن عمر رضي الله عنه قال") == "عن عمر قال"
    assert normalize_hadith_search("عن عائشة رضي الله عنها وعن ابن عباس رضي الله عنهما") == "عن عائشة وعن ابن عباس"
    assert normalize_hadith_search("ﻗﺎﻝ") == "قال"          # Arabic presentation forms -> base letters


def test_quran_normalization_is_unchanged():
    assert normalize_for_search("قال رسول الله ﷺ") == "قال رسول الله ﷺ"   # norm-v1 untouched
    assert hadith_tokens("") == []


@pytest.mark.real_corpus
@pytest.mark.parametrize("quote", [
    "سمعت رسول الله ﷺ يقول: «إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى»",
    "سمعت رسول الله صلى الله عليه وسلم يقول إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "سمعت رسول الله يقول إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "سمعتُ رسولَ اللهِ صلّى الله عليه وسلّم يقولُ: إنّما الأعمالُ بالنّيّاتِ وإنّما لكلِّ امرئٍ ما نوى",
])
def test_honorific_variants_find_the_same_hadith(real_db, real_repo, quote):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, quote, "ادعاء")
    assert r.source is not None and r.source.source_type == "hadith"
    assert r.context.matched[0].passage_id == "hadith:bukhari:1"
    # the displayed hadith is the stored text, unchanged (with the honorific written out)
    shown = r.context.matched[0].text
    assert shown == real_repo.get("hadith:bukhari:1").original_text and "صلى الله عليه وسلم" in shown


@pytest.mark.real_corpus
def test_slice_cut_inside_an_honorific_still_matches(real_db, real_repo):
    """A verbatim slice ending in the middle of «صلى الله عليه وسلم» matches via the plain search copy."""
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, "عمر بن الخطاب رضي الله عنه على المنبر قال سمعت رسول الله صلى الله", "ادعاء")
    assert r.quote_analysis.match_status in ("PARTIAL", "AMBIGUOUS")
    assert r.quote_analysis.ambiguity_reason != "NEAR_MATCH_UNCONFIRMED"
