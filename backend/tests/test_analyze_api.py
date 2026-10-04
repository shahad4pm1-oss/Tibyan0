import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.connection import connect
from app.main import create_app
from app.repositories.corpus import CorpusRepository


def client_for(monkeypatch, db, **env):
    monkeypatch.setenv("DATABASE_PATH", str(db))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear():
    yield
    get_settings.cache_clear()


# ---- synthetic corpus (hash TEST DOUBLE for semantic)


def test_resolved_synthetic(monkeypatch, synthetic_db):
    with client_for(monkeypatch, synthetic_db, EMBEDDING_PROVIDER="hash", EMBEDDING_MODEL="") as c:
        r = c.post("/api/v1/analyze", json={"quote": "ملخصا قصيرا في دفتره", "claim": "ادعاء تجريبي", "language": "ar"})
        j = r.json()
        assert r.status_code == 200 and j["status"] == "RESOLVED"
        assert j["quote_analysis"]["match_status"] == "PARTIAL"
        assert j["source"]["source_id"] == "synth" and j["source"]["reference"] == "1:3"
        assert [u["passage_id"] for u in j["context"]["before"]] == ["synth:1:1", "synth:1:2"]
        assert j["evidence"]["items"][0] == {**j["evidence"]["items"][0], "id": "E1", "role": "matched_source"}
        assert j["claim"]["text"] == "ادعاء تجريبي"
        # Phase 3 contract (replaces the Phase 2 NOT_IMPLEMENTED placeholder): with no LLM configured,
        # the claim is never judged and no verdict label is produced.
        ca = j["claim_analysis"]
        assert ca["status"] == "ANALYSIS_UNAVAILABLE" and ca["relation"] is None
        assert ca["summary_source"] == "system_template" and ca["gate"]["decision"] == "PASS"
        assert j["metadata"]["llm_provider"] is None and j["metadata"]["llm_unavailable_reason"]
        for bad in ("SUPPORTED", "OVERSTATED", "CONTRADICTED", "REQUIRES_SPECIALIST", "INSUFFICIENT_EVIDENCE"):
            assert bad not in r.text


def test_ambiguous_and_not_found(monkeypatch, synthetic_db):
    with client_for(monkeypatch, synthetic_db, EMBEDDING_PROVIDER="hash", EMBEDDING_MODEL="") as c:
        a = c.post("/api/v1/analyze", json={"quote": "الى البيت قبل غروب الشمس", "claim": "ادعاء"}).json()
        assert a["status"] == "AMBIGUOUS_SOURCE" and a["quote_analysis"]["alternatives_total"] == 2
        assert a["source"] is None and a["evidence"]["items"] == []
        n = c.post("/api/v1/analyze", json={"quote": "اشترى المهندس حاسوبا جديدا", "claim": "ادعاء"}).json()
        assert n["status"] == "SOURCE_NOT_FOUND" and n["quote_analysis"]["match_status"] == "NOT_FOUND"


def test_degraded_lexical_only(monkeypatch, synthetic_db):
    with client_for(monkeypatch, synthetic_db, EMBEDDING_PROVIDER="local_lsa") as c:  # no LSA model in fixture dir
        j = c.post("/api/v1/analyze", json={"quote": "ملخصا قصيرا في دفتره", "claim": "ادعاء"}).json()
        assert j["status"] == "RESOLVED"
        assert j["metadata"]["search_mode"] == "LEXICAL_ONLY" and j["metadata"]["degraded_reason"]
        assert any(w["code"] == "SEMANTIC_SEARCH_UNAVAILABLE" for w in j["warnings"])
        assert c.get("/health").json()["search_mode"] == "LEXICAL_ONLY"


@pytest.mark.parametrize("body", [
    {"quote": "hello world", "claim": "xx"},
    {"quote": "", "claim": "ادعاء"},
    {"quote": "نص عربي", "claim": ""},
    {"quote": "نص عربي", "claim": "ادعاء", "language": "en"},
    {"quote": "ن" * 2001, "claim": "ادعاء"},
    {"claim": "ادعاء"},
])
def test_invalid_input(monkeypatch, synthetic_db, body):
    with client_for(monkeypatch, synthetic_db, EMBEDDING_PROVIDER="hash", EMBEDDING_MODEL="") as c:
        r = c.post("/api/v1/analyze", json=body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INPUT"
        assert "Traceback" not in r.text


def test_corpus_not_available(monkeypatch, tmp_path):
    with client_for(monkeypatch, tmp_path / "missing.sqlite3") as c:
        r = c.post("/api/v1/analyze", json={"quote": "نص عربي", "claim": "ادعاء"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "CORPUS_NOT_AVAILABLE"
        assert c.get("/health").json()["corpus_available"] is False


def test_internal_error_is_safe(monkeypatch, synthetic_db):
    with client_for(monkeypatch, synthetic_db, EMBEDDING_PROVIDER="hash", EMBEDDING_MODEL="") as c:
        def boom(*a, **k):
            raise RuntimeError("secret internal detail")
        monkeypatch.setattr(c.app.state.pipeline, "analyze", boom)
        r = c.post("/api/v1/analyze", json={"quote": "نص عربي", "claim": "ادعاء"})
        assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "secret internal detail" not in r.text and "Traceback" not in r.text


# ---- real corpus (REAL local LSA model)


@pytest.mark.real_corpus
def test_real_api_resolved_span(monkeypatch, real_db):
    repo = CorpusRepository(connect(real_db, readonly=True))
    w190 = repo.get("quran:2:190").metadata["publisher_aya_text_emlaey"].split()
    w191 = repo.get("quran:2:191").metadata["publisher_aya_text_emlaey"].split()
    with client_for(monkeypatch, real_db, EMBEDDING_PROVIDER="local_lsa", EMBEDDING_MODEL="char-ngram-lsa-v1") as c:
        j = c.post("/api/v1/analyze", json={"quote": " ".join(w190[-3:] + w191[:3]), "claim": "ادعاء"}).json()
        assert j["status"] == "RESOLVED" and j["source"]["reference"] == "2:190-191"
        assert [u["passage_id"] for u in j["context"]["matched"]] == ["quran:2:190", "quran:2:191"]
        for u in j["context"]["before"] + j["context"]["matched"] + j["context"]["after"]:
            assert u["text"] == repo.get(u["passage_id"]).original_text
        assert j["metadata"]["search_mode"] == "HYBRID" and "TEST DOUBLE" not in j["metadata"]["embedding_model"]
        assert j["metadata"]["corpus_version"].startswith("c2-quran-hafs2.0u13")
        assert repo.source("quran")["corpus_version"] == "c1-kfgqpc-hafs-2.0u13"  # Quran source unchanged
