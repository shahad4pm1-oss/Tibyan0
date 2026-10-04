"""Tafsir al-Tabari loader (Quran.com API v4), async, with in-memory cache and non-crashing fallbacks.

Endpoint: GET {API_BASE_URL}/tafsirs/{resource_id}/by_ayah/{surah}:{ayah}
Default resource id 15 = Arabic "Tafsir al-Tabari" on Quran.com.

Read before relying on it:
* Not run against the live API (the build environment has no network); it was exercised against a stub
  transport only. Resource id 15 and the response shape come from the public Quran.com v4 docs. Every
  result carries the `resource_id` / `resource_name` the API actually returned so the attribution can be
  checked, and a response whose resource id differs from the requested one is rejected.
* al-Tabari died in 310 AH. If the competition rule is a strict "first three hijri centuries" cut-off,
  confirm with the organisers that his work qualifies.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, replace

import httpx

log = logging.getLogger("tibyan.tafsir_loader")

API_BASE_URL = "https://api.quran.com/api/v4"
TABARI_RESOURCE_ID = 15
MIN_SURAH, MAX_SURAH = 1, 114

ERRORS: dict[str, tuple[str, str]] = {
    "INVALID_INPUT": ("surah_num must be 1-114 and ayah_num a positive integer.",
                      "رقم السورة (١–١١٤) أو رقم الآية غير صالح."),
    "NOT_FOUND": ("No Tafsir al-Tabari entry was found for this ayah.",
                  "لم يوجد تفسير الطبري لهذه الآية."),
    "RATE_LIMITED": ("The Tafsir service is limiting requests. Please try again shortly.",
                     "خدمة التفسير تحدّ من الطلبات حاليًا. أعد المحاولة بعد قليل."),
    "TIMEOUT": ("The Tafsir service did not respond in time. Please try again.",
                "لم تستجب خدمة التفسير في الوقت المحدد. أعد المحاولة."),
    "UNAVAILABLE": ("The Tafsir service is currently unavailable. Please try again later.",
                    "خدمة التفسير غير متاحة حاليًا. أعد المحاولة لاحقًا."),
    "BAD_RESPONSE": ("The Tafsir service returned an unexpected response.",
                     "أعادت خدمة التفسير استجابة غير متوقعة."),
}

_BLOCK_RE = re.compile(r"</?(?:p|br|div|h[1-6]|li|ul|ol)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACES_RE = re.compile(r"[ \t\u00a0]+")
_BLANKS_RE = re.compile(r"\n{3,}")


def _clean(raw: str) -> str:
    """HTML -> plain text; paragraph breaks kept; angle brackets removed so the text cannot forge prompt tags."""
    text = _BLOCK_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("<", "").replace(">", "")
    text = _SPACES_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANKS_RE.sub("\n\n", text).strip()


@dataclass(frozen=True)
class TafsirResult:
    ok: bool
    surah: int | None = None
    ayah: int | None = None
    text: str = ""
    resource_id: int | None = None
    resource_name: str | None = None
    covers: tuple[str, ...] = ()      # ayah keys the returned passage covers (Tabari groups ayat), e.g. ("2:1", "2:2")
    truncated: bool = False
    cached: bool = False
    error_code: str | None = None
    error: str | None = None          # English, safe to show
    error_ar: str | None = None       # Arabic, safe to show

    def to_dict(self) -> dict:
        return asdict(self)


def _failure(code: str, surah: int | None = None, ayah: int | None = None) -> TafsirResult:
    en, ar = ERRORS[code]
    return TafsirResult(ok=False, surah=surah, ayah=ayah, error_code=code, error=en, error_ar=ar)


def _as_int(value) -> int | None:
    if isinstance(value, (bool, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TabariTafsirManager:
    """Fetches the Tafsir of one ayah. `get_ayah_context` never raises: failures come back as TafsirResult(ok=False)."""

    def __init__(self, *, resource_id: int = TABARI_RESOURCE_ID, base_url: str = API_BASE_URL,
                 timeout_s: float = 10.0, max_retries: int = 2, backoff_s: float = 0.5,
                 cache_size: int = 512, max_concurrency: int = 5, max_chars: int | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.resource_id = int(resource_id)
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        self.max_retries = max(0, int(max_retries))
        self.backoff_s = max(0.0, float(backoff_s))
        self.cache_size = max(1, int(cache_size))
        self.max_chars = max_chars
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._cache: OrderedDict[tuple[int, int], TafsirResult] = OrderedDict()
        self._inflight: dict[tuple[int, int], asyncio.Task] = {}
        self._sem = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------ lifecycle
    async def __aenter__(self) -> "TabariTafsirManager":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001  closing must never raise
                log.debug("tafsir client close failed", exc_info=True)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_s, connect=min(5.0, self.timeout_s)),
                headers={"Accept": "application/json", "User-Agent": "Tibyan/0.5 tafsir-loader"},
                transport=self._transport, follow_redirects=False)
        return self._client

    # ------------------------------------------------------------------ cache
    def clear_cache(self) -> None:
        self._cache.clear()

    def cache_info(self) -> dict:
        return {"size": len(self._cache), "max_size": self.cache_size, "hits": self._hits, "misses": self._misses}

    def _cache_get(self, key: tuple[int, int]) -> TafsirResult | None:
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
        return hit

    def _cache_put(self, key: tuple[int, int], result: TafsirResult) -> None:
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    # ------------------------------------------------------------------ public API
    async def get_ayah_context(self, surah_num: int, ayah_num: int) -> TafsirResult:
        surah, ayah = _as_int(surah_num), _as_int(ayah_num)
        if surah is None or ayah is None or not MIN_SURAH <= surah <= MAX_SURAH or ayah < 1:
            return _failure("INVALID_INPUT", surah, ayah)
        key = (surah, ayah)
        try:
            hit = self._cache_get(key)
            if hit is not None:
                self._hits += 1
                return replace(hit, cached=True)
            self._misses += 1
            task = self._inflight.get(key)       # concurrent callers for one ayah share a single request
            if task is None:
                task = asyncio.ensure_future(self._fetch(surah, ayah))
                self._inflight[key] = task
                task.add_done_callback(lambda _t, k=key: self._inflight.pop(k, None))
            return await asyncio.shield(task)
        except Exception:  # noqa: BLE001  last line of defence: callers must never crash on a tafsir lookup
            log.exception("unexpected tafsir loader failure for %s:%s", surah, ayah)
            return _failure("UNAVAILABLE", surah, ayah)

    # ------------------------------------------------------------------ internals
    async def _fetch(self, surah: int, ayah: int) -> TafsirResult:
        path = f"/tafsirs/{self.resource_id}/by_ayah/{surah}:{ayah}"
        last_code = "UNAVAILABLE"
        for attempt in range(self.max_retries + 1):
            delay = self.backoff_s * (2 ** attempt)
            try:
                async with self._sem:
                    resp = await self._get_client().get(path)
            except httpx.TimeoutException:
                last_code = "TIMEOUT"
            except httpx.HTTPError as exc:
                last_code = "UNAVAILABLE"
                log.warning("tafsir request failed (%s) for %s:%s", type(exc).__name__, surah, ayah)
            except Exception as exc:  # noqa: BLE001
                log.warning("tafsir request error (%s) for %s:%s", type(exc).__name__, surah, ayah)
                return _failure("UNAVAILABLE", surah, ayah)
            else:
                status = resp.status_code
                if status == 200:
                    result = self._parse(resp, surah, ayah)
                    if result.ok:
                        self._cache_put((surah, ayah), result)
                    return result
                if status in (400, 404):
                    return _failure("NOT_FOUND", surah, ayah)
                if status == 429:
                    last_code = "RATE_LIMITED"
                    retry_after = _as_int(resp.headers.get("Retry-After"))
                    if retry_after is not None:
                        delay = min(max(retry_after, 0), 5)
                elif status >= 500:
                    last_code = "UNAVAILABLE"
                else:
                    log.warning("tafsir API answered HTTP %s for %s:%s", status, surah, ayah)
                    return _failure("UNAVAILABLE", surah, ayah)
            if attempt < self.max_retries:
                await asyncio.sleep(delay)
        return _failure(last_code, surah, ayah)

    def _parse(self, resp: httpx.Response, surah: int, ayah: int) -> TafsirResult:
        try:
            payload = resp.json()
        except ValueError:
            return _failure("BAD_RESPONSE", surah, ayah)
        tafsir = payload.get("tafsir") if isinstance(payload, dict) else None
        if not isinstance(tafsir, dict):
            return _failure("BAD_RESPONSE", surah, ayah)

        returned_id = _as_int(tafsir.get("resource_id"))
        if returned_id is not None and returned_id != self.resource_id:
            log.error("tafsir resource mismatch: asked %s, got %s", self.resource_id, returned_id)
            return _failure("BAD_RESPONSE", surah, ayah)   # never present another work as al-Tabari

        raw = tafsir.get("text")
        text = _clean(raw) if isinstance(raw, str) else ""
        if not text:
            return _failure("NOT_FOUND", surah, ayah)
        truncated = False
        if self.max_chars is not None and len(text) > self.max_chars:
            text, truncated = text[: self.max_chars].rstrip() + " […]", True

        verses = tafsir.get("verses")
        name = tafsir.get("resource_name")
        return TafsirResult(
            ok=True, surah=surah, ayah=ayah, text=text,
            resource_id=returned_id if returned_id is not None else self.resource_id,
            resource_name=name if isinstance(name, str) else None,
            covers=tuple(str(k) for k in verses) if isinstance(verses, dict) else (f"{surah}:{ayah}",),
            truncated=truncated)


# ---------------------------------------------------------------------- sync adapter for the pipeline
TABARI_BOOK_AR = "تفسير الطبري (جامع البيان عن تأويل آي القرآن)"


class TabariTafsirSource:
    """Synchronous, LocalTafsirCorpus-compatible view of TabariTafsirManager for the evidence builder.

    The async manager (shared client, LRU cache, retries) lives on one private event-loop thread, so the
    synchronous pipeline can call `get_tafsir()` from any worker thread. Never raises: a failed lookup
    returns '' and is recorded in `last_error` (the caller can then fall back to another tafsir)."""

    def __init__(self, manager: TabariTafsirManager | None = None, *, call_timeout_s: float = 15.0, **kwargs):
        import threading

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="tabari-tafsir", daemon=True)
        self._thread.start()
        self.call_timeout_s = call_timeout_s
        # the manager's semaphore must be created on its own loop
        self.manager = manager or asyncio.run_coroutine_threadsafe(self._make(kwargs), self._loop).result()
        self.last_error: dict[tuple[int, int], str] = {}
        self._names: dict[int, str] = {}
        # while the service is failing, skip it for FAILURE_COOLDOWN_S so every request is not slowed down
        self._down_until = 0.0

    @staticmethod
    async def _make(kwargs: dict) -> TabariTafsirManager:
        return TabariTafsirManager(**kwargs)

    def lookup(self, surah_id: int, ayah_id: int) -> TafsirResult:
        fut = asyncio.run_coroutine_threadsafe(self.manager.get_ayah_context(surah_id, ayah_id), self._loop)
        try:
            return fut.result(timeout=self.call_timeout_s)
        except Exception:  # noqa: BLE001  timeout or loop failure: never crash the pipeline
            fut.cancel()
            return _failure("TIMEOUT", _as_int(surah_id), _as_int(ayah_id))

    FAILURE_COOLDOWN_S = 120.0

    def get_tafsir(self, surah_id: int, ayah_id: int) -> str:
        import time

        if time.monotonic() < self._down_until:
            self.last_error[(int(surah_id), int(ayah_id))] = "COOLDOWN"
            return ""
        r = self.lookup(surah_id, ayah_id)
        if not r.ok:
            self.last_error[(int(surah_id), int(ayah_id))] = r.error_code or "UNAVAILABLE"
            if r.error_code in ("TIMEOUT", "UNAVAILABLE", "RATE_LIMITED"):
                self._down_until = time.monotonic() + self.FAILURE_COOLDOWN_S
            return ""
        return r.text

    def get_source_name(self, surah_id: int) -> str | None:
        return TABARI_BOOK_AR

    def describe(self) -> dict | None:
        rid = self.manager.resource_id
        return {"id": f"tabari-{rid}", "name": TABARI_BOOK_AR, "author": {"name": "محمد بن جرير الطبري (ت ٣١٠هـ)"},
                "edition": f"Quran.com API v4, resource {rid}", "nasher": "Quran.com", "dump_version": "live API",
                "ayahs": 6236, "live_api": True}

    def close(self) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.manager.aclose(), self._loop).result(timeout=5)
        except Exception:  # noqa: BLE001
            log.debug("tabari source close failed", exc_info=True)
        self._loop.call_soon_threadsafe(self._loop.stop)


class ChainedTafsir:
    """First tafsir source that has an entry wins (e.g. al-Tabari, then the local Tafsir Mujahid files).
    The book name reported for an ayah is always the book whose text was returned for it."""

    def __init__(self, *sources):
        self.sources = [s for s in sources if s is not None]
        self._book: dict[tuple[int, int], str | None] = {}

    def get_tafsir(self, surah_id: int, ayah_id: int) -> str:
        for s in self.sources:
            text = s.get_tafsir(surah_id, ayah_id)
            if text:
                self._book[(int(surah_id), int(ayah_id))] = s.get_source_name(surah_id)
                return text
        return ""

    def get_source_name(self, surah_id: int, ayah_id: int | None = None) -> str | None:
        if ayah_id is not None and (int(surah_id), int(ayah_id)) in self._book:
            return self._book.pop((int(surah_id), int(ayah_id)))
        return self.sources[0].get_source_name(surah_id) if self.sources else None

    def describe(self) -> dict | None:
        return next((d for d in (s.describe() for s in self.sources) if d), None)

    def describe_all(self) -> list[dict]:
        return [d for d in (s.describe() for s in self.sources) if d]
