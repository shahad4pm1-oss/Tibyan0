"""Phase 4 API end-to-end flows on the REAL production corpus, with production settings and NO LLM configured.

Every quote is read from the database (never typed), except the deliberately non-Quran sentence.
"""

import io
import logging
import shutil

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.connection import connect
from app.main import create_app
from app.repositories.corpus import CorpusRepository

pytestmark = pytest.mark.real_corpus

NO_LLM = "تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً"
PROD = {"APP_ENV": "production", "CORS_ORIGINS": "https://tibyan.example.org", "EMBEDDING_PROVIDER": "local_lsa",
        "EMBEDDING_MODEL": "char-ngram-lsa-v1", "RATE_LIMIT_PER_MINUTE": "100000", "LLM_PROVIDER": "", "LLM_API_KEY": ""}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def prod_client(monkeypatch, db, **extra):
    monkeypatch.setenv("DATABASE_PATH", str(db))
    for k, v in {**PROD, **extra}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.fixture()
def emlaey(real_db):
    repo = CorpusRepository(connect(real_db, readonly=True))
    return lambda pid: repo.get(pid).metadata["publisher_aya_text_emlaey"], repo


def post(c, quote, claim="هذا النص من القرآن"):
    r = c.post("/api/v1/analyze", json={"quote": quote, "claim": claim, "language": "ar"})
    assert r.status_code == 200, r.text
    return r.json()


def assert_no_llm(j):
    ca = j["claim_analysis"]
    assert ca["summary_source"] != "ai"
    assert j["metadata"]["llm_provider"] is None and j["metadata"]["llm_model"] is None
    assert ca["attempts"] == 0


def test_health_production_no_llm(monkeypatch, real_db):
    with prod_client(monkeypatch, real_db) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["app_env"] == "production" and h["config_problems"] == []
        corpus = h["components"]["corpus"]
        assert corpus["by_source_type"]["quran"] == 6236 and corpus["integrity_ok"]
        assert corpus["by_source_type"]["hadith"] == 7380 + 2922 + 192 and "terms" not in corpus
        assert h["components"]["llm"] == {**h["components"]["llm"], "configured": False, "mode": "LLM_UNAVAILABLE"}
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_exact_quote_no_llm(monkeypatch, real_db, emlaey):
    em, repo = emlaey
    with prod_client(monkeypatch, real_db) as c:
        j = post(c, em("quran:1:2"), "هذا النص من سورة الفاتحة")
    assert j["quote_analysis"]["match_status"] == "EXACT" and j["source"]["reference"] == "1:2"
    assert j["context"]["matched"][0]["text"] == repo.get("quran:1:2").original_text
    assert j["claim_analysis"]["status"] == "ANALYSIS_UNAVAILABLE" and j["claim_analysis"]["relation"] is None
    assert j["claim_analysis"]["summary"].startswith(NO_LLM)
    assert_no_llm(j)


def test_partial_quote_with_context(monkeypatch, real_db, emlaey):
    em, _ = emlaey
    with prod_client(monkeypatch, real_db) as c:
        j = post(c, " ".join(em("quran:2:191").split()[:4]), "الآية تأمر بقتل غير المسلمين مطلقا")
    assert j["quote_analysis"]["match_status"] == "PARTIAL" and j["source"]["reference"] == "2:191"
    assert [u["passage_id"] for u in j["context"]["before"]] == ["quran:2:189", "quran:2:190"]
    assert j["evidence"]["strength"] in ("LIMITED", "SUFFICIENT")
    assert j["claim_analysis"]["status"] in ("ANALYSIS_UNAVAILABLE", "REFERRED")
    assert_no_llm(j)


def test_ambiguous_repeated_text_not_attributed(monkeypatch, real_db, emlaey):
    em, _ = emlaey
    with prod_client(monkeypatch, real_db) as c:
        j = post(c, em("quran:55:13"), "هذه الآية وردت مرة واحدة")
    qa = j["quote_analysis"]
    assert qa["match_status"] == "AMBIGUOUS" and qa["ambiguity_reason"] == "MULTIPLE_LOCATIONS"
    assert j["source"] is None and j["context"]["matched"] == [] and qa["alternatives_total"] >= 30
    assert all(a["passage_id"].startswith("quran:55:") for a in qa["alternatives"])
    assert j["claim_analysis"]["relation"] == "INSUFFICIENT_EVIDENCE" and j["claim_analysis"]["summary_source"] == "system_template"


def test_near_match_unconfirmed(monkeypatch, real_db, emlaey):
    em, _ = emlaey
    words = em("quran:2:255").split()[:8]
    words[3] = "الرحيم"  # one-word substitution
    with prod_client(monkeypatch, real_db) as c:
        j = post(c, " ".join(words))
    qa = j["quote_analysis"]
    assert qa["match_status"] in ("AMBIGUOUS", "NOT_FOUND") and j["source"] is None
    if qa["match_status"] == "AMBIGUOUS":
        assert qa["ambiguity_reason"] == "NEAR_MATCH_UNCONFIRMED"
        assert "quran:2:255" in [a["passage_id"] for a in qa["alternatives"]]


def test_unknown_text_not_found(monkeypatch, real_db):
    with prod_client(monkeypatch, real_db) as c:
        j = post(c, "من جد وجد ومن زرع حصد")
    assert j["quote_analysis"]["match_status"] == "NOT_FOUND" and j["status"] == "SOURCE_NOT_FOUND"
    assert j["source"] is None and j["evidence"]["strength"] == "INSUFFICIENT"


def test_lexical_only_when_semantic_index_missing(monkeypatch, real_db, emlaey, tmp_path):
    em, _ = emlaey
    shutil.copy(real_db, tmp_path / real_db.name)  # DB only, no FAISS/LSA files next to it
    with prod_client(monkeypatch, tmp_path / real_db.name) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["search_mode"] == "LEXICAL_ONLY"  # ok: corpus + lexical ready
        assert h["components"]["semantic_index"]["ready"] is False
        j = post(c, em("quran:112:1"))
    assert j["metadata"]["search_mode"] == "LEXICAL_ONLY"
    assert [w["code"] for w in j["warnings"]] == ["SEMANTIC_SEARCH_UNAVAILABLE"]
    assert j["quote_analysis"]["match_status"] in ("EXACT", "AMBIGUOUS")


@pytest.mark.parametrize("body", [{}, {"quote": "", "claim": "x"}, {"quote": "ا" * 5000, "claim": "x"},
                                  {"quote": "abc", "claim": "x", "language": "xx"}])
def test_invalid_input_production(monkeypatch, real_db, body):
    with prod_client(monkeypatch, real_db) as c:
        r = c.post("/api/v1/analyze", json=body)
    assert r.status_code in (413, 422) and r.json()["error"]["code"] in ("INVALID_INPUT", "PAYLOAD_TOO_LARGE")
    assert "Traceback" not in r.text


def test_raw_input_never_logged(monkeypatch, real_db, emlaey):
    em, _ = emlaey
    quote, claim = em("quran:1:2"), "ادعاء سري لا يجب أن يظهر في السجل"
    buf = io.StringIO()
    with prod_client(monkeypatch, real_db) as c:
        h = logging.getLogger("tibyan").handlers[0]
        old = h.setStream(buf)
        try:
            post(c, quote, claim)
        finally:
            h.setStream(old)
    log = buf.getvalue()
    assert "tibyan.audit" in log and claim not in log and quote not in log


def test_methodology_and_evaluation(monkeypatch, real_db):
    with prod_client(monkeypatch, real_db) as c:
        m = c.get("/api/v1/methodology").json()
        e = c.get("/api/v1/evaluation").json()
    assert m["llm_is_a_source"] is False and m["llm"]["configured"] is False
    assert {s["source_type"] for s in m["sources"]} == {"quran", "hadith", "tafsir"}
    assert all(s["verification_status"] == "APPROVED" and (s["source_url"] or s["provenance"]) for s in m["sources"] if s["source_type"] != "tafsir")  # tafsir is commentary, listed with its own status
    assert m["analysis_enabled_source_types"] == ["quran"]
    assert m["source"]["package_sha256"] == "a7b0e5591945712ec5e4d6142938ae4d1e9b49bdc89dff06222789bfebdfd72c"
    assert e["llm"].get("status") == "PENDING_REAL_MODEL_VALIDATION"
    assert e["classification"]["status"] == "NOT_COMPUTED" and e["classification"]["reviewed_cases"] == 0
    assert "Not model performance" in e["guard_rails"]["label"]
