"""Local tafsir corpus (lazy loading) and the separated Quran/tafsir evidence layer."""

import json

import pytest

from app.corpus.tafsir import LocalTafsirCorpus
from app.services.claim_analyzer import PromptSet
from app.services.context_expander import ContextWindow
from app.services.evidence_builder import (
    QURAN_LABEL,
    TAFSIR_LABEL,
    TAFSIR_SEPARATION_DIRECTIVE,
    EvidenceBuilder,
    format_evidence_text,
    has_tafsir_layer,
)
from app.services.types import Passage


def _write(d, n, slug, ayahs):
    (d / f"{n:03d}_{slug}.json").write_text(json.dumps(
        {"book": {"name": "تفسير تجريبي"}, "surah": n, "ayahs": ayahs}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def tafsir_dir(tmp_path):
    _write(tmp_path, 1, "a", [{"ayah": 1, "content": [{"text": 'شرح <span class="x">الآية</span> الأولى'}]}])
    _write(tmp_path, 2, "b", [{"ayah": 5, "content": [{"text": "أ"}, {"text": "ب"}]}])
    _write(tmp_path, 3, "c", [])
    return tmp_path


def test_lazy_loading_and_lru(tafsir_dir):
    c = LocalTafsirCorpus(tafsir_dir, cache_size=1)
    assert c.cached_surahs == []                      # nothing is read at construction
    assert c.get_tafsir(1, 1) == "شرح الآية الأولى"   # markup stripped
    assert c.cached_surahs == [1]
    assert c.get_tafsir(2, 5) == "أ\n\nب"
    assert c.cached_surahs == [2]                     # surah 1 evicted
    assert c.get_source_name(2) == "تفسير تجريبي"


def test_missing_data_returns_empty_and_bad_input_raises(tafsir_dir):
    c = LocalTafsirCorpus(tafsir_dir)
    assert c.get_tafsir(1, 99) == "" and c.get_tafsir(3, 1) == "" and c.get_tafsir(50, 1) == ""
    assert LocalTafsirCorpus(tafsir_dir / "nope").get_tafsir(1, 1) == ""
    for bad in ((0, 1), (115, 1), (1, 0)):
        with pytest.raises(ValueError):
            c.get_tafsir(*bad)


def test_exact_competition_format():
    assert format_evidence_text("آية", "شرح") == f"{QURAN_LABEL}: آية \n\n {TAFSIR_LABEL}: شرح"
    assert format_evidence_text("آية", "شرح") == "[النص القرآني]: آية \n\n [تفسير الآية]: شرح"


def _passage(surah, ayah, text="نص الآية"):
    return Passage(id=f"quran:{surah}:{ayah}", rowid=1, source_id="quran", reference=f"{surah}:{ayah}", sequence=1,
                   parent_id=f"quran:{surah}", original_text=text, normalized_text=text, normalized_text_alt=None,
                   metadata={"surah_number": surah, "ayah_number": ayah})


SRC = {"id": "quran", "title": "القرآن", "edition": "e", "source_type": "quran", "verification_status": "APPROVED"}


def test_builder_adds_separated_commentary_item(tafsir_dir):
    p = _passage(1, 1)
    items = EvidenceBuilder(LocalTafsirCorpus(tafsir_dir)).build(ContextWindow(matched=[p]), SRC)
    assert [e.role for e in items] == ["matched_source", "source_commentary", "metadata"]
    assert items[0].text == p.original_text                      # canonical ayah stays untouched
    assert items[1].text == "[النص القرآني]: نص الآية \n\n [تفسير الآية]: شرح الآية الأولى"
    assert items[1].passage_id is None and has_tafsir_layer(items)


def test_builder_without_tafsir_or_for_other_sources_is_unchanged(tafsir_dir):
    p = _passage(1, 1)
    assert [e.role for e in EvidenceBuilder().build(ContextWindow(matched=[p]), SRC)] == ["matched_source", "metadata"]
    other = {**SRC, "source_type": "hadith"}
    assert [e.role for e in EvidenceBuilder(LocalTafsirCorpus(tafsir_dir)).build(
        ContextWindow(matched=[p]), other)] == ["matched_source", "metadata"]
    # no entry for this ayah -> no commentary item
    assert [e.role for e in EvidenceBuilder(LocalTafsirCorpus(tafsir_dir)).build(
        ContextWindow(matched=[_passage(1, 7)]), SRC)] == ["matched_source", "metadata"]


def test_long_tafsir_is_truncated_and_flagged(tmp_path):
    _write(tmp_path, 1, "a", [{"ayah": 1, "content": [{"text": "كلمة " * 500}]}])
    items = EvidenceBuilder(LocalTafsirCorpus(tmp_path), tafsir_max_chars=100).build(
        ContextWindow(matched=[_passage(1, 1)]), SRC)
    c = items[1]
    assert c.metadata["tafsir_truncated"] is True and c.text.endswith("[…]")


def test_system_prompt_carries_the_separation_directive():
    assert TAFSIR_SEPARATION_DIRECTIVE in PromptSet.load("claim_analysis_v1").system
    assert QURAN_LABEL in TAFSIR_SEPARATION_DIRECTIVE and TAFSIR_LABEL in TAFSIR_SEPARATION_DIRECTIVE


def test_describe_reports_book_and_ayah_count(tmp_path):
    _write(tmp_path, 1, "a", [{"ayah": 1, "content": [{"text": "x"}]}, {"ayah": 2, "content": [{"text": "y"}]}])
    d = LocalTafsirCorpus(tmp_path).describe()
    assert d["name"] == "تفسير تجريبي" and d["ayahs"] == 2
    assert LocalTafsirCorpus(tmp_path / "missing").describe() is None


def test_request_timeout_covers_the_llm_budget():
    from app.core.config import Settings
    s = Settings(_env_file=None, llm_provider="gemini", llm_timeout_s=60, request_timeout_s=45)
    assert s.effective_request_timeout_s == 135                 # call + one retry + processing
    assert Settings(_env_file=None, llm_provider=None, request_timeout_s=45).effective_request_timeout_s == 45
