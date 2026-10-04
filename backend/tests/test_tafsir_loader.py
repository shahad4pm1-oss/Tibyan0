"""TabariTafsirManager: parsing, cache, retries and non-crashing fallbacks (no network: scripted transport)."""

import asyncio
import json

import httpx
import pytest

from app.corpus.tafsir_loader import TABARI_RESOURCE_ID, TabariTafsirManager


class Script(httpx.AsyncBaseTransport):
    """Replays scripted responses/exceptions; the last step repeats."""

    def __init__(self, *steps):
        self.steps, self.paths = list(steps), []

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step


def ok(text="<p>قال أبو جعفر: تأويل</p><p>الثاني &amp; ختام</p>", rid=TABARI_RESOURCE_ID, verses=None):
    body = {"tafsir": {"resource_id": rid, "resource_name": "تفسير الطبري", "text": text,
                       "verses": verses or {"2:255": {}, "2:256": {}}}}
    return httpx.Response(200, content=json.dumps(body).encode("utf-8"))


def make(*steps, **kw):
    t = Script(*steps)
    return TabariTafsirManager(transport=t, backoff_s=0, **kw), t


def run(coro):
    return asyncio.run(coro)


def test_success_cleans_html_and_uses_the_tabari_endpoint():
    m, t = make(ok())
    r = run(m.get_ayah_context(2, 255))
    assert r.ok and r.text == "قال أبو جعفر: تأويل\n\nالثاني & ختام"
    assert t.paths[0].endswith(f"/tafsirs/{TABARI_RESOURCE_ID}/by_ayah/2:255")
    assert r.covers == ("2:255", "2:256") and r.resource_name == "تفسير الطبري" and not r.cached


def test_second_call_is_served_from_cache():
    async def go():
        m, t = make(ok())
        await m.get_ayah_context(2, 255)
        r = await m.get_ayah_context(2, 255)
        return m, t, r
    m, t, r = run(go())
    assert r.cached and len(t.paths) == 1 and m.cache_info()["hits"] == 1


def test_concurrent_calls_share_one_request():
    async def go():
        m, t = make(ok())
        rs = await asyncio.gather(*[m.get_ayah_context(3, 1) for _ in range(6)])
        return rs, t
    rs, t = run(go())
    assert all(r.ok for r in rs) and len(t.paths) == 1


def test_not_found_is_clean_and_not_retried():
    m, t = make(httpx.Response(404))
    r = run(m.get_ayah_context(2, 999))
    assert not r.ok and r.error_code == "NOT_FOUND" and r.error and r.error_ar and len(t.paths) == 1


def test_server_errors_are_retried_then_reported_without_raising():
    m, t = make(httpx.Response(500), httpx.Response(503), httpx.Response(500))
    r = run(m.get_ayah_context(1, 1))
    assert r.error_code == "UNAVAILABLE" and len(t.paths) == 3


def test_transient_failure_then_success():
    m, t = make(httpx.Response(500), ok())
    assert run(m.get_ayah_context(1, 1)).ok and len(t.paths) == 2


def test_timeout_and_connection_errors_become_error_results():
    m, t = make(httpx.ReadTimeout("slow"))
    assert run(m.get_ayah_context(1, 1)).error_code == "TIMEOUT" and len(t.paths) == 3
    m, _ = make(httpx.ConnectError("down"))
    assert run(m.get_ayah_context(1, 1)).error_code == "UNAVAILABLE"
    m, _ = make(RuntimeError("boom"))
    assert run(m.get_ayah_context(1, 1)).error_code == "UNAVAILABLE"


def test_rate_limit_honours_retry_after_and_reports_when_persistent():
    m, _ = make(httpx.Response(429, headers={"Retry-After": "0"}), ok())
    assert run(m.get_ayah_context(1, 1)).ok
    m, _ = make(httpx.Response(429))
    assert run(m.get_ayah_context(1, 1)).error_code == "RATE_LIMITED"


@pytest.mark.parametrize("body", [b"<html>", b"[]", b'{"tafsir": 5}', b'{"tafsir": {"text": ""}}'])
def test_malformed_bodies_do_not_crash(body):
    m, _ = make(httpx.Response(200, content=body))
    r = run(m.get_ayah_context(1, 1))
    assert not r.ok and r.error_code in ("BAD_RESPONSE", "NOT_FOUND")


def test_another_tafsir_is_never_presented_as_tabari():
    m, _ = make(ok(rid=14))
    assert run(m.get_ayah_context(1, 1)).error_code == "BAD_RESPONSE"


@pytest.mark.parametrize("args", [(0, 1), (115, 1), (1, 0), ("x", 1), (None, None), (True, 1), (1.5, 2)])
def test_invalid_input_returns_error_without_a_request(args):
    m, t = make(ok())
    assert run(m.get_ayah_context(*args)).error_code == "INVALID_INPUT" and t.paths == []


def test_lru_eviction_truncation_and_to_dict():
    async def go():
        m, _ = make(ok("x" * 50), cache_size=2, max_chars=10)
        for a in (1, 2, 3):
            r = await m.get_ayah_context(2, a)
        async with m:
            pass
        return m, r
    m, r = run(go())
    assert m.cache_info()["size"] == 2 and r.truncated and r.text.endswith("[…]") and r.to_dict()["ok"] is True
