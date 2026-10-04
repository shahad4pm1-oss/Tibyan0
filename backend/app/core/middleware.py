"""Pure-ASGI middleware: request ids, body-size limit, security headers, in-process rate limiting.

Rate limiting is a per-process sliding window keyed by client IP. Hackathon-scale only: it resets on
restart, is not shared across workers or instances, and behind a proxy depends on TRUST_PROXY_HEADERS
(X-Forwarded-For). See docs/SECURITY.md.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque

from app.core.errors import MESSAGES

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


def _error_body(code: str, rid: str) -> bytes:
    ar, en = MESSAGES[code]
    return json.dumps({"request_id": rid, "error": {"code": code, "message_ar": ar, "message_en": en,
                                                    "details": None}}, ensure_ascii=False).encode()


async def _send_error(send, status: int, code: str, rid: str, extra: list | None = None) -> None:
    body = _error_body(code, rid)
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"x-request-id", rid.encode())] + SECURITY_HEADERS + (extra or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    """Assigns a request id (scope['state']['request_id']) and adds X-Request-ID + security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = rid

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                present = {h[0].lower() for h in headers}
                headers.append((b"x-request-id", rid.encode()))
                headers += [h for h in SECURITY_HEADERS if h[0] not in present]
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_wrapped)


class BodySizeLimitMiddleware:
    """Rejects bodies larger than max_bytes with 413, by Content-Length or by counting streamed chunks."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        rid = scope.get("state", {}).get("request_id", str(uuid.uuid4()))
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    if int(v) > self.max_bytes:
                        return await _send_error(send, 413, "PAYLOAD_TOO_LARGE", rid)
                except ValueError:
                    return await _send_error(send, 413, "PAYLOAD_TOO_LARGE", rid)
        chunks, total = [], 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return None
            total += len(msg.get("body", b""))
            if total > self.max_bytes:
                return await _send_error(send, 413, "PAYLOAD_TOO_LARGE", rid)
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


class RateLimiter:
    def __init__(self, per_minute: int, window_s: float = 60.0):
        self.per_minute = per_minute
        self.window = window_s
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if self.per_minute <= 0:
            return True, 0
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.per_minute:
                return False, max(1, int(self.window - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > 10000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True, 0


class RateLimitMiddleware:
    def __init__(self, app, limiter: RateLimiter, paths: tuple[str, ...], trust_proxy: bool):
        self.app = app
        self.limiter = limiter
        self.paths = paths
        self.trust_proxy = trust_proxy

    def _client(self, scope) -> str:
        if self.trust_proxy:
            for k, v in scope.get("headers", []):
                if k == b"x-forwarded-for":
                    return v.decode("latin-1").split(",")[0].strip()
        c = scope.get("client")
        return c[0] if c else "unknown"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] in self.paths:
            ok, retry = self.limiter.check(self._client(scope))
            if not ok:
                rid = scope.get("state", {}).get("request_id", str(uuid.uuid4()))
                return await _send_error(send, 429, "RATE_LIMITED", rid, [(b"retry-after", str(retry).encode())])
        return await self.app(scope, receive, send)
