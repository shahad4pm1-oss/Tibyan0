import pytest

from app.services.lexical_retriever import LexicalRetriever
from app.services.quote_matcher import QuoteMatcher, coverage
from app.services.rank_fusion import lexical_first
from app.services.types import MatchStatus


def run(repo, q, mode="disabled"):
    cands = lexical_first(LexicalRetriever(repo, 20).search(q), [], top_n=10)
    return QuoteMatcher(repo, paraphrase_mode=mode).match(q, cands)


def test_coverage_unit():
    assert coverage(["a", "b", "c"], ["x", "a", "b", "c", "y"]) == 1.0
    assert coverage(["a", "b", "z"], ["a", "b", "c"]) == pytest.approx(2 / 3)
    assert coverage([], ["a"]) == 0.0


# ---- synthetic corpus


def test_exact(synthetic_repo):
    m = run(synthetic_repo, "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ")
    assert m.status is MatchStatus.EXACT and [p.id for p in m.passages] == ["synth:1:3"]


def test_partial(synthetic_repo):
    m = run(synthetic_repo, "ملخصا قصيرا في دفتره")
    assert m.status is MatchStatus.PARTIAL and m.passages[0].id == "synth:1:3"


def test_span_across_items(synthetic_repo):
    m = run(synthetic_repo, "في دفتره الازرق وعاد الى البيت")
    assert m.status is MatchStatus.PARTIAL and m.method == "span"
    assert [p.id for p in m.passages] == ["synth:1:3", "synth:1:4"]


def test_near_match_is_not_attributed_by_default(synthetic_repo):
    m = run(synthetic_repo, "لعب الاطفال بالكرة قرب النهر")
    assert m.status is MatchStatus.AMBIGUOUS and m.passages == []
    assert m.reason.value == "NEAR_MATCH_UNCONFIRMED"
    assert "synth:2:2" in {p.id for p in m.alternatives}


def test_paraphrased_only_in_experimental_mode(synthetic_repo):
    m = run(synthetic_repo, "لعب الاطفال بالكرة قرب النهر", mode="experimental")
    assert m.status is MatchStatus.PARAPHRASED and m.passages[0].id == "synth:2:2"


def test_ambiguous_repeated_phrase(synthetic_repo):
    m = run(synthetic_repo, "الى البيت قبل غروب الشمس")
    assert m.status is MatchStatus.AMBIGUOUS
    assert {p.id for p in m.alternatives} == {"synth:1:4", "synth:2:4"}


def test_not_found(synthetic_repo):
    assert run(synthetic_repo, "اشترى المهندس حاسوبا جديدا للمختبر").status is MatchStatus.NOT_FOUND


def test_never_matches_pending_or_rejected(synthetic_repo):
    assert run(synthetic_repo, "القطارات البرتقالية").status is MatchStatus.NOT_FOUND
    assert run(synthetic_repo, "الطائرات البنفسجية").status is MatchStatus.NOT_FOUND


def test_short_single_word_not_resolved(synthetic_repo):
    assert run(synthetic_repo, "البيت").status in (MatchStatus.AMBIGUOUS, MatchStatus.NOT_FOUND)


# ---- real corpus


@pytest.mark.real_corpus
def test_real_exact_partial_span(real_repo):
    p190, p191 = real_repo.get("quran:2:190"), real_repo.get("quran:2:191")
    assert run(real_repo, p191.original_text).status is MatchStatus.EXACT
    w = p191.metadata["publisher_aya_text_emlaey"].split()
    assert run(real_repo, " ".join(w[:4])).status is MatchStatus.PARTIAL
    q = " ".join(p190.metadata["publisher_aya_text_emlaey"].split()[-4:] + w[:4])
    m = run(real_repo, q)
    assert m.status is MatchStatus.PARTIAL and [p.id for p in m.passages] == ["quran:2:190", "quran:2:191"]


@pytest.mark.real_corpus
def test_real_repeated_ayah_ambiguous(real_repo):
    m = run(real_repo, real_repo.get("quran:55:13").original_text)
    assert m.status is MatchStatus.AMBIGUOUS and m.alternatives_total > 1


@pytest.mark.real_corpus
def test_real_misquote_is_not_attributed(real_repo):
    w = real_repo.get("quran:2:191").metadata["publisher_aya_text_emlaey"].split()[:8]
    w[3] = "الناس"
    m = run(real_repo, " ".join(w))
    assert m.status is MatchStatus.AMBIGUOUS and m.passages == []
    assert "quran:2:191" in {p.id for p in m.alternatives}  # shown for review, not attributed
