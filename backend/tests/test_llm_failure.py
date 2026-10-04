"""Provider failures degrade safely; the Anthropic adapter is tested with a mock HTTP transport
(NOT the live API)."""

import json
import logging

import httpx
import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMEmptyResponse, LLMProviderError, LLMTimeout
from app.schemas.claim_analysis import provider_json_schema

from .conftest import ask, good_output, make_pipeline

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"
CLAIM = "النص يذكر الملخص"


@pytest.mark.parametrize("err,cat", [(LLMTimeout("t"), "TIMEOUT"), (LLMProviderError("HTTP 500"), "PROVIDER_ERROR"),
                                     (LLMEmptyResponse("e"), "EMPTY_RESPONSE")])
def test_provider_errors_no_verdict_but_source_kept(synthetic_db, err, cat):
    p = make_pipeline(synthetic_db, [err])
    r = ask(p, EXACT, CLAIM)
    ca = r.claim_analysis
    assert ca.status == "ANALYSIS_UNAVAILABLE" and ca.relation is None and ca.uncertainty_reason.split(":")[0] == cat  # category, then the provider detail
    assert r.source.reference == "1:3" and r.context.matched and r.evidence.items  # source verification kept
    assert len(p.llm.calls) == 1  # no retry on provider errors


@pytest.mark.parametrize("bad", ["{not json", "", "[]", json.dumps({"relation": "SUPPORTED"}),
                                 json.dumps(good_output(ids=("E40",)))])
def test_invalid_outputs_twice_abstain(synthetic_db, bad):
    p = make_pipeline(synthetic_db, [bad, bad])
    r = ask(p, EXACT, CLAIM)
    assert r.claim_analysis.status == "AI_OUTPUT_REJECTED" and r.claim_analysis.relation == "INSUFFICIENT_EVIDENCE"
    assert r.source is not None


def test_no_provider_configured(synthetic_db):
    p = make_pipeline(synthetic_db, provider=None)
    r = ask(p, EXACT, CLAIM)
    assert r.claim_analysis.status == "ANALYSIS_UNAVAILABLE" and r.claim_analysis.relation is None


# ---- Anthropic adapter (mock transport)

def _transport(handler):
    return httpx.MockTransport(handler)


def test_adapter_request_shape_and_parsing():
    seen = {}

    def h(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={
            "content": [{"type": "thinking", "thinking": "PRIVATE"}, {"type": "text", "text": '{"a": 1}'}],
            "usage": {"input_tokens": 120, "output_tokens": 30}, "stop_reason": "end_turn"})

    p = AnthropicProvider("model-x", "sk-test-SECRET", base_url="https://example.invalid", transport=_transport(h))
    r = p.complete_json("SYS", "USER", provider_json_schema(), 512)
    assert seen["url"] == "https://example.invalid/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-test-SECRET" and seen["headers"]["anthropic-version"] == "2023-06-01"
    b = seen["body"]
    assert b["model"] == "model-x" and b["system"] == "SYS" and b["messages"] == [{"role": "user", "content": "USER"}]
    assert b["output_config"]["format"]["type"] == "json_schema" and b["max_tokens"] == 512
    assert r.text == '{"a": 1}' and "PRIVATE" not in r.text  # non-text blocks discarded
    assert (r.usage.input_tokens, r.usage.output_tokens) == (120, 30)
    assert "SECRET" not in repr(p)


def test_adapter_errors():
    def h500(req):
        return httpx.Response(500, json={"error": "x"})

    def htimeout(req):
        raise httpx.ReadTimeout("slow")

    def hempty(req):
        return httpx.Response(200, json={"content": [], "usage": {}})

    for h, exc in ((h500, LLMProviderError), (htimeout, LLMTimeout), (hempty, LLMEmptyResponse)):
        p = AnthropicProvider("m", "k", base_url="https://example.invalid", transport=_transport(h))
        with pytest.raises(exc):
            p.complete_json("s", "u", {}, 10)


def test_adapter_never_reads_anthropic_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://should-not-be-used.invalid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    from app.core.config import Settings
    from app.llm.factory import build_provider
    st = build_provider(Settings(llm_provider="anthropic", llm_model="m"))
    assert st.provider is None and st.reason == "LLM_API_KEY not set"
    st = build_provider(Settings(llm_provider="anthropic", llm_model="m", llm_api_key="k"))
    assert str(st.provider._client.base_url).startswith("https://api.anthropic.com")


def test_adapter_error_does_not_log_key(caplog):
    def h(req):
        return httpx.Response(401, json={"error": "bad key"})
    p = AnthropicProvider("m", "sk-SECRET-123", base_url="https://example.invalid", transport=_transport(h))
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMProviderError) as e:
        p.complete_json("s", "u", {}, 10)
    assert "SECRET" not in str(e.value) and "SECRET" not in caplog.text


def test_env_example_parses_with_empty_values():
    from pathlib import Path

    from app.core.config import Settings
    s = Settings(_env_file=str(Path(__file__).resolve().parents[2] / ".env.example"))
    assert s.llm_provider is None and s.llm_temperature is None and s.llm_price_input_per_mtok is None
