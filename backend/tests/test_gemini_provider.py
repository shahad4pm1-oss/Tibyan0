"""Gemini adapter: request shape, parsing, errors and secret handling, against an HTTP mock transport.
No network. The live API is checked only by eval/provider_health.py with a real key."""

import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.llm.base import LLMEmptyResponse, LLMProviderError, LLMTimeout
from app.llm.factory import build_provider
from app.llm.gemini_provider import DEFAULT_BASE_URL, GeminiProvider
from app.schemas.claim_analysis import minimal_json_schema

from .conftest import ask, good_minimal, good_output, make_pipeline

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


def _ok(text='{"ok": true}', **extra):
    body = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4}}
    body.update(extra)
    return httpx.Response(200, json=body)


def _prov(handler, **kw):
    return GeminiProvider("gemini-test-model", "AIza-TEST-SECRET", base_url="https://example.invalid",
                          transport=httpx.MockTransport(handler), **kw)


def test_request_shape_and_parsing():
    seen = {}

    def h(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-goog-api-key")
        seen["body"] = json.loads(req.content)
        return _ok()

    r = _prov(h, temperature=0.0).complete_json("SYS", "USER", SCHEMA, 1024)
    assert seen["url"] == "https://example.invalid/v1beta/models/gemini-test-model:generateContent"
    assert seen["key"] == "AIza-TEST-SECRET"
    b = seen["body"]
    assert b["systemInstruction"] == {"parts": [{"text": "SYS"}]}
    assert b["contents"] == [{"role": "user", "parts": [{"text": "USER"}]}]
    g = b["generationConfig"]
    assert g["responseMimeType"] == "application/json" and g["responseJsonSchema"] == SCHEMA
    assert g["maxOutputTokens"] >= 1024 and g["temperature"] == 0.0
    assert "key" not in seen["url"]  # key goes in a header, never in the URL
    assert r.text == '{"ok": true}' and r.usage.input_tokens == 11 and r.usage.output_tokens == 4
    assert r.stop_reason == "STOP"


def test_models_prefix_is_accepted():
    seen = {}

    def h(req):
        seen["path"] = req.url.path
        return _ok()

    GeminiProvider("models/gemini-x", "k", base_url="https://example.invalid",
                   transport=httpx.MockTransport(h)).complete_json("s", "u", SCHEMA)
    assert seen["path"] == "/v1beta/models/gemini-x:generateContent"


def test_thought_parts_are_discarded():
    def h(req):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "hidden reasoning", "thought": True}, {"text": '{"ok": true}'}]}, "finishReason": "STOP"}]})

    assert _prov(h).complete_json("s", "u", SCHEMA).text == '{"ok": true}'


def test_schema_rejection_falls_back_to_json_mode_once():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            return httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                       "message": "Invalid JSON payload: responseJsonSchema ..."}})
        return _ok()

    r = _prov(h).complete_json("s", "u", SCHEMA)
    assert r.text == '{"ok": true}' and len(bodies) == 2
    assert "responseJsonSchema" in bodies[0]["generationConfig"]
    assert "responseJsonSchema" not in bodies[1]["generationConfig"]
    assert bodies[1]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize("status,payload,expect", [
    (400, {"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid.",
                     "details": [{"reason": "API_KEY_INVALID"}]}}, "HTTP 400 INVALID_ARGUMENT API_KEY_INVALID"),
    (403, {"error": {"status": "PERMISSION_DENIED", "message": "x"}}, "HTTP 403 PERMISSION_DENIED"),
    (404, {"error": {"status": "NOT_FOUND", "message": "models/x is not found"}}, "HTTP 404 NOT_FOUND"),
    (429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}}, "HTTP 429 RESOURCE_EXHAUSTED"),
    (503, {"error": {"status": "UNAVAILABLE", "message": "overloaded"}}, "HTTP 503 UNAVAILABLE"),
])
def test_http_errors_report_codes_only(status, payload, expect):
    calls = []

    def h(req):
        if req.method == "POST":
            calls.append(1)
        return httpx.Response(status, json=payload)

    with pytest.raises(LLMProviderError) as e:
        _prov(h).complete_json("s", "u", SCHEMA)
    # codes first; a 404 then adds the model-list diagnosis (see test_404_lists_models_the_key_can_use)
    assert str(e.value) == expect or (status == 404 and str(e.value).startswith(expect + "; "))
    assert "TEST-SECRET" not in str(e.value)
    assert len(calls) == 1  # no schema fallback unless the error names the schema


def test_timeout_and_transport_errors():
    def slow(req):
        raise httpx.ReadTimeout("t", request=req)

    def down(req):
        raise httpx.ConnectError("c", request=req)

    with pytest.raises(LLMTimeout):
        _prov(slow).complete_json("s", "u", SCHEMA)
    with pytest.raises(LLMProviderError, match="transport error: ConnectError"):
        _prov(down).complete_json("s", "u", SCHEMA)


def test_blocked_or_empty_output_is_an_empty_response():
    def blocked(req):
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    def empty(req):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]})

    with pytest.raises(LLMEmptyResponse, match="SAFETY"):
        _prov(blocked).complete_json("s", "u", SCHEMA)
    with pytest.raises(LLMEmptyResponse, match="MAX_TOKENS"):
        _prov(empty).complete_json("s", "u", SCHEMA)


def test_key_never_in_repr_errors_or_logs(caplog):
    def h(req):
        return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "bad AIza-TEST-SECRET"}})

    p = _prov(h)
    assert "SECRET" not in repr(p)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(LLMProviderError) as e:
        p.complete_json("s", "u", SCHEMA)
    assert "SECRET" not in str(e.value)
    assert "SECRET" not in caplog.text


def test_adapter_never_reads_google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "env-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")
    st = build_provider(Settings(_env_file=None, llm_provider="gemini", llm_model="m"))
    assert st.provider is None and st.reason == "LLM_API_KEY not set"


@pytest.mark.parametrize("name", ["gemini", "google", "Gemini"])
def test_factory_builds_gemini(name):
    st = build_provider(Settings(_env_file=None, llm_provider=name, llm_model="gemini-x", llm_api_key="k"))
    assert isinstance(st.provider, GeminiProvider) and st.provider.provider == "gemini"
    assert str(st.provider._client.base_url).rstrip("/") == DEFAULT_BASE_URL


def test_factory_ignores_old_anthropic_base_url_for_gemini():
    st = build_provider(Settings(_env_file=None, llm_provider="gemini", llm_model="m", llm_api_key="k",
                                 llm_base_url="https://api.anthropic.com"))
    assert str(st.provider._client.base_url).rstrip("/") == DEFAULT_BASE_URL


def test_factory_anthropic_default_url_unchanged():
    st = build_provider(Settings(_env_file=None, llm_provider="anthropic", llm_model="m", llm_api_key="k"))
    assert str(st.provider._client.base_url).rstrip("/") == "https://api.anthropic.com"


# ---- Gemini adapter inside the real pipeline (synthetic corpus, mocked HTTP; no network)
EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"
CLAIM = "النص يذكر الملخص"


def _gemini_answering(texts, seen):
    def h(req):
        seen.append(json.loads(req.content))
        return _ok(texts[min(len(seen), len(texts)) - 1])
    return GeminiProvider("gemini-test-model", "AIza-TEST-SECRET", base_url="https://example.invalid",
                          transport=httpx.MockTransport(h))


def test_pipeline_with_gemini_structured_output_completes(synthetic_db):
    seen = []
    p = make_pipeline(synthetic_db, provider=_gemini_answering([json.dumps(good_minimal(), ensure_ascii=False)], seen))
    r = ask(p, EXACT, CLAIM)
    ca = r.claim_analysis
    assert ca.status == "COMPLETED" and ca.relation == "SUPPORTED" and ca.summary_source == "ai"
    assert ca.evidence_ids == ["E1"] and ca.verdict == "correct" and ca.assertions[0].label == "supported"
    assert r.metadata.llm_provider == "gemini" and r.metadata.llm_model == "gemini-test-model"
    assert seen[0]["generationConfig"]["responseJsonSchema"] == minimal_json_schema()
    sent = json.dumps(seen[0], ensure_ascii=False)
    assert "E1" in sent and "AIza-TEST-SECRET" not in sent  # evidence goes to the model, the key never in the body


def test_pipeline_with_gemini_rejects_ungrounded_output(synthetic_db):
    seen = []
    bad = json.dumps(good_output(ids=("E40",)), ensure_ascii=False)  # cites evidence that does not exist
    p = make_pipeline(synthetic_db, provider=_gemini_answering([bad, bad], seen))
    r = ask(p, EXACT, CLAIM)
    assert r.claim_analysis.status == "AI_OUTPUT_REJECTED" and len(seen) == 2
    assert r.source is not None  # source verification kept


# ---- Gemma models on the same API: no system instruction, no JSON mode
def _gemma(handler, model="gemma-3-27b-it"):
    return GeminiProvider(model, "AIza-TEST-SECRET", base_url="https://example.invalid",
                          transport=httpx.MockTransport(handler))


def test_gemma_sends_plain_request():
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        return _ok('```json\n{"ok": true}\n```')
    _gemma(h).complete_json("SYSTEM RULES", "USER DATA", {"type": "object"})
    body = seen[0]
    assert "systemInstruction" not in body
    assert "responseMimeType" not in body["generationConfig"] and "responseJsonSchema" not in body["generationConfig"]
    text = body["contents"][0]["parts"][0]["text"]
    assert text.index("SYSTEM RULES") < text.index("USER DATA")


def test_unsupported_instruction_error_switches_to_plain_mode():
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        if len(seen) == 1:
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT",
                                                       "message": "Developer instruction is not enabled for this model"}})
        return _ok('{"ok": true}')
    p = _gemma(h, model="some-new-model")
    assert p.complete_json("S", "U", {"type": "object"}).text == '{"ok": true}'
    assert "systemInstruction" in seen[0] and "systemInstruction" not in seen[1] and p.plain_mode


def test_pipeline_with_gemma_completes(synthetic_db):
    answer = "Here is the result:\n" + json.dumps(good_minimal(), ensure_ascii=False) + "\nDone."
    p = make_pipeline(synthetic_db, provider=_gemma(lambda req: _ok(answer)))
    ca = ask(p, EXACT, CLAIM).claim_analysis
    assert ca.status == "COMPLETED" and ca.verdict == "correct" and r_model(p) == "gemma-3-27b-it"


def r_model(p):
    return p.llm.model


def test_404_lists_models_the_key_can_use():
    def h(req):
        if req.method == "GET":
            assert req.headers["x-goog-api-key"] == "AIza-TEST-SECRET"
            return httpx.Response(200, json={"models": [
                {"name": "models/gemma-3-27b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]})
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": "models/x is not found"}})
    with pytest.raises(LLMProviderError) as e:
        _gemma(h, model="gemma-4-26b-a4b-it").complete_json("S", "U", {"type": "object"})
    msg = str(e.value)
    assert "HTTP 404 NOT_FOUND" in msg and "available: gemma-3-27b-it" in msg and "AIza" not in msg


def test_404_with_bad_key_points_at_the_key():
    def h(req):
        if req.method == "GET":
            return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
    with pytest.raises(LLMProviderError) as e:
        _gemma(h).complete_json("S", "U", {"type": "object"})
    assert "check LLM_API_KEY" in str(e.value)
