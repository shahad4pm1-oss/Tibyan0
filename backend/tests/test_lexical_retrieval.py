import pytest

from app.services.lexical_retriever import LexicalRetriever
from app.services.normalizer import normalize_for_search

# ---- synthetic (non-religious) corpus


def top(repo, q):
    r = LexicalRetriever(repo, 20).search(q)
    return r[0].passage.id if r else None


def test_exact(synthetic_repo):
    assert top(synthetic_repo, "قَرَأَ كِتَابًا عَنِ البِحَارِ وَالأَسْمَاكِ المُلَوَّنَةِ") == "synth:1:2"


def test_without_diacritics(synthetic_repo):
    assert top(synthetic_repo, "قرا كتابا عن البحار والاسماك الملونة") == "synth:1:2"


def test_partial(synthetic_repo):
    assert top(synthetic_repo, "دفتره الازرق") == "synth:1:3"


def test_extra_whitespace(synthetic_repo):
    assert top(synthetic_repo, "   لعب    الاطفال   بالكرة   ") == "synth:2:2"


def test_formatting_differences(synthetic_repo):
    assert top(synthetic_repo, "«لَعِبَ الأطفالُ بالكرة» (2)") == "synth:2:2"


def test_not_found(synthetic_repo):
    assert LexicalRetriever(synthetic_repo, 20).search("حاسوب برمجيات خوارزمية") == []


def test_result_fields(synthetic_repo):
    c = LexicalRetriever(synthetic_repo, 20).search("المكتبة")[0]
    assert c.passage.id and c.passage.source_id and c.passage.reference and c.passage.original_text
    assert c.lexical_rank == 1 and c.lexical_score is not None


def test_top_k_respected(synthetic_repo):
    assert len(LexicalRetriever(synthetic_repo, 2).search("الى البيت قبل")) <= 2


# ---- real corpus (text read from the database, never typed)


@pytest.mark.real_corpus
@pytest.mark.parametrize("pid", ["quran:1:2", "quran:2:255", "quran:36:1", "quran:112:1"])
def test_real_exact_uthmani_and_imlaei(real_repo, pid):
    p = real_repo.get(pid)
    lr = LexicalRetriever(real_repo, 20)
    assert pid in [c.passage.id for c in lr.search(p.original_text)[:5]]
    assert pid in [c.passage.id for c in lr.search(p.metadata["publisher_aya_text_emlaey"])[:5]]


@pytest.mark.real_corpus
def test_real_partial_and_whitespace(real_repo):
    p = real_repo.get("quran:2:191")
    w = p.metadata["publisher_aya_text_emlaey"].split()
    res = LexicalRetriever(real_repo, 20).search("   " + "   ".join(w[2:7]) + "  ")
    assert res[0].passage.id == "quran:2:191"


@pytest.mark.real_corpus
def test_real_query_is_normalized_same_as_index(real_repo):
    p = real_repo.get("quran:3:7")
    assert normalize_for_search(p.original_text) == p.normalized_text_alt
