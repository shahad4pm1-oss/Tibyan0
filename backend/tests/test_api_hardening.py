"""Phase 4 API hardening: request ids, safe errors, limits, rate limiting, CORS, production profile, health,
methodology/evaluation endpoints, FTS query robustness."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.middleware import RateLimiter
from app.main import create_app
from app.services.analysis_pipeline import AnalysisPipeline, CorpusNotAvailable

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"


@pytest.fixture()
def client(monkeypatch, synthetic_db):
    def make(**env):
        base = {"DATABASE_PATH": str(synthetic_db), "EMBEDDING_PROVIDER": "hash", "EMBEDDING_MODEL": "",
                "RATE_LIMIT_PER_MINUTE": "0"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return TestClient(create_app())
    yield make
    get_settings.cache_clear()


def test_request_id_and_security_headers(client):
    with client() as c:
        r = c.post("/api/v1/analyze", json={"quote": EXACT, "claim": "النص يذكر الملخص"})
        assert r.status_code == 200 and r.headers["x-request-id"] == r.json()["request_id"]
        for h in ("x-content-type-options", "x-frame-options", "referrer-policy", "cache-control"):
            assert h in r.headers
        bad = c.post("/api/v1/analyze", json={"quote": "x"})
        assert bad.status_code == 422 and bad.headers["x-request-id"] == bad.json()["request_id"]


def test_unknown_route_and_method_are_safe_json(client):
    with client() as c:
        r = c.get("/nope")
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        r = c.get("/api/v1/analyze")
        assert r.status_code == 405 and r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert "Traceback" not in r.text


def test_body_size_limit(client):
    with client(MAX_BODY_BYTES="2000") as c:
        r = c.post("/api/v1/analyze", content=b'{"quote":"' + "ن".encode() * 3000 + b'","claim":"x"}',
                   headers={"content-type": "application/json"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_malformed_json_is_invalid_input(client):
    with client() as c:
        r = c.post("/api/v1/analyze", content=b"{not json", headers={"content-type": "application/json"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INPUT"


def test_rate_limit(client):
    with client(RATE_LIMIT_PER_MINUTE="3") as c:
        codes = [c.post("/api/v1/analyze", json={"quote": EXACT, "claim": "النص يذكر"}).status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
        r = c.post("/api/v1/analyze", json={"quote": EXACT, "claim": "النص يذكر"})
        assert r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) >= 1
        assert c.get("/health").status_code == 200  # health is not rate limited


def test_rate_limiter_window():
    rl = RateLimiter(2, window_s=10)
    assert rl.check("a", 0)[0] and rl.check("a", 1)[0] and not rl.check("a", 2)[0]
    assert rl.check("b", 2)[0]  # per key
    assert rl.check("a", 11)[0]  # window slides


def test_timeout(client, monkeypatch):
    import time
    with client(REQUEST_TIMEOUT_S="0.2") as c:
        monkeypatch.setattr(c.app.state.pipeline, "analyze", lambda *a, **k: time.sleep(1))
        r = c.post("/api/v1/analyze", json={"quote": EXACT, "claim": "النص"})
        assert r.status_code == 504 and r.json()["error"]["code"] == "TIMEOUT"


@pytest.mark.parametrize("quote", ['"ملخصا" OR "قصيرا"', "ملخصا NEAR(قصيرا)", "normalized_text: ملخصا",
                                   "ملخصا AND NOT قصيرا", "ملخصا*", "^ملخصا", "'; DROP TABLE passages; -- ملخصا",
                                   "ملخصا {x} [y] (z)", "ملخصا \\u0000"])
def test_fts_and_sql_injection_inputs_are_safe(client, quote):
    with client() as c:
        r = c.post("/api/v1/analyze", json={"quote": quote, "claim": "ادعاء"})
        assert r.status_code == 200, r.text
        assert c.get("/health").json()["components"]["corpus"]["passages"] > 0  # nothing dropped


def test_health_components_no_llm(client):
    with client() as c:
        h = c.get("/health").json()
        assert h["status"] == "ok"
        comp = h["components"]
        assert comp["database"]["ready"] and comp["corpus"]["integrity_ok"] and comp["lexical_search"]["ready"]
        assert comp["semantic_index"]["ready"] is True
        assert comp["llm"]["configured"] is False and comp["llm"]["mode"] == "LLM_UNAVAILABLE"
        assert "key" not in str(h).lower() or "api_key" not in str(h).lower()


def test_health_corpus_missing(client, tmp_path):
    with client(DATABASE_PATH=str(tmp_path / "missing.sqlite3")) as c:
        h = c.get("/health").json()
        assert h["status"] == "unavailable" and h["corpus_available"] is False


def test_methodology_and_evaluation_endpoints(client):
    with client() as c:
        m = c.get("/api/v1/methodology").json()
        assert m["llm_is_a_source"] is False and "not a source" in m["statement"]
        assert m["versions"]["paraphrase_mode"] == "disabled" and len(m["pipeline"]) >= 10
        e = c.get("/api/v1/evaluation").json()
        assert e["classification"]["status"] == "NOT_COMPUTED"
        assert e["llm"]["status"] in ("PENDING_REAL_MODEL_VALIDATION", "COMPLETED")
        if e["guard_rails"]:
            assert "TEST-DOUBLE" in e["guard_rails"]["label"]


def test_production_cors_and_docs(monkeypatch):
    s = Settings(app_env="production", cors_origins="*, http://localhost:5173, https://tibyan.example.org")
    assert s.cors_origin_list == ["https://tibyan.example.org"]
    assert Settings(app_env="development", cors_origins="http://localhost:5173").cors_origin_list == \
        ["http://localhost:5173"]
    assert "CORS_ORIGINS has no explicit https frontend origin" in \
        Settings(app_env="production", cors_origins="*").production_problems()
    assert "LLM_PROVIDER is a test double" in Settings(app_env="production", llm_provider="test_double",
                                                        cors_origins="https://a.org").production_problems()
    assert Settings(app_env="production", cors_origins="https://a.org").production_problems() == []


def test_production_hides_docs_and_refuses_fixture_corpus(client, synthetic_db):
    with client(APP_ENV="production", CORS_ORIGINS="https://a.org", RATE_LIMIT_PER_MINUTE="30") as c:
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
        assert c.get("/health").json()["status"] == "unavailable"  # synthetic corpus refused
    with pytest.raises(CorpusNotAvailable):
        AnalysisPipeline(Settings(app_env="production", database_path=str(synthetic_db)), synthetic_db.parent)


def test_production_cors_preflight(client):
    with client(APP_ENV="development", CORS_ORIGINS="https://tibyan.example.org") as c:
        ok = c.options("/api/v1/analyze", headers={"Origin": "https://tibyan.example.org",
                                                    "Access-Control-Request-Method": "POST"})
        bad = c.options("/api/v1/analyze", headers={"Origin": "https://evil.example",
                                                     "Access-Control-Request-Method": "POST"})
        assert ok.headers.get("access-control-allow-origin") == "https://tibyan.example.org"
        assert "access-control-allow-origin" not in bad.headers
