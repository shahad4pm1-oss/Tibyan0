"""Tafsir al-Tabari wired into the evidence layer (no network: scripted transport)."""

import httpx
import pytest

from app.corpus.tafsir import LocalTafsirCorpus
from app.corpus.tafsir_loader import TABARI_BOOK_AR, ChainedTafsir, TabariTafsirSource
from app.schemas.claim_analysis import LLMClaimOutput
from app.services import citation_verifier
from app.services.context_expander import ContextWindow
from app.services.evidence_builder import TAFSIR_LABEL, EvidenceBuilder

from .conftest import ask, good_minimal, good_output, make_pipeline
from .test_tafsir_evidence import _passage, _write
from .test_tafsir_loader import Script, ok

SRC = {"id": "kfgqpc", "title": "القرآن", "edition": "حفص", "source_type": "quran", "verification_status": "APPROVED"}


def tabari(*steps):
    return TabariTafsirSource(transport=Script(*steps), backoff_s=0, max_retries=0)


@pytest.fixture
def local_dir(tmp_path):
    _write(tmp_path, 2, "b", [{"ayah": 5, "content": [{"text": "شرح محلي"}]}])
    return tmp_path


def _p(s, a):
    return _passage(s, a)


def test_source_returns_tabari_text():
    t = tabari(ok("<p>قال أبو جعفر: معناه كذا</p>"))
    assert t.get_tafsir(2, 255) == "قال أبو جعفر: معناه كذا" and t.get_source_name(2) == TABARI_BOOK_AR
    t.close()


def test_source_failure_is_empty_not_an_exception():
    t = tabari(httpx.Response(503), httpx.ConnectError("down"))
    assert t.get_tafsir(2, 255) == "" and t.last_error[(2, 255)] in ("UNAVAILABLE", "TIMEOUT")
    t.close()


def test_chain_prefers_tabari_and_falls_back_to_local(local_dir):
    local = LocalTafsirCorpus(local_dir)
    c = ChainedTafsir(tabari(ok("<p>تأويل الطبري</p>")), local)
    assert c.get_tafsir(2, 5) == "تأويل الطبري" and c.get_source_name(2, 5) == TABARI_BOOK_AR
    c = ChainedTafsir(tabari(httpx.Response(404)), local)
    assert c.get_tafsir(2, 5) == "شرح محلي" and c.get_source_name(2, 5) == "تفسير تجريبي"


def test_evidence_carries_tabari_layer(local_dir):
    c = ChainedTafsir(tabari(ok("<p>تأويل الطبري</p>")), LocalTafsirCorpus(local_dir))
    items = EvidenceBuilder(c).build(ContextWindow(matched=[_p(2, 5)]), SRC)
    t = next(e for e in items if e.role == "source_commentary")
    assert t.metadata["tafsir_book"] == TABARI_BOOK_AR and f"{TAFSIR_LABEL}: تأويل الطبري" in t.text
    assert items[0].text == "نص الآية"  # the matched ayah itself is untouched


def test_naming_tabari_is_grounded_only_when_supplied(local_dir):
    out = LLMClaimOutput.model_validate(good_output("SUPPORTED", ids=("E2",), reason="E2 يذكر الطبري أن المعنى كذا"))
    with_tabari = EvidenceBuilder(ChainedTafsir(tabari(ok("<p>تأويل</p>")))).build(
        ContextWindow(matched=[_p(2, 5)]), SRC)
    assert "UNSUPPORTED_SOURCE_MENTION" not in citation_verifier.verify(out, with_tabari)
    local_only = EvidenceBuilder(LocalTafsirCorpus(local_dir)).build(ContextWindow(matched=[_p(2, 5)]), SRC)
    assert "UNSUPPORTED_SOURCE_MENTION" in citation_verifier.verify(out, local_only)


def test_pipeline_builds_tabari_chain_from_settings(synthetic_db):
    p = make_pipeline(synthetic_db, [], tafsir_provider="tabari")
    assert isinstance(p.tafsir, ChainedTafsir) and isinstance(p.tafsir.sources[0], TabariTafsirSource)
    assert isinstance(p.tafsir.sources[1], LocalTafsirCorpus)
    assert isinstance(make_pipeline(synthetic_db, [], tafsir_provider="local").tafsir, LocalTafsirCorpus)


@pytest.mark.real_corpus
def test_real_pipeline_sends_tabari_to_model(real_db, real_quote):
    p = make_pipeline(real_db, [good_minimal()], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    p.builder.tafsir = ChainedTafsir(tabari(ok("<p>قال أبو جعفر: تأويل هذه الآية</p>")))
    r = ask(p, real_quote, "الآية تذكر القتال")
    assert any(e.metadata and e.metadata.get("tafsir_book") == TABARI_BOOK_AR for e in r.evidence.items)
    assert "قال أبو جعفر: تأويل هذه الآية" in p.llm.calls[0]["user"]
