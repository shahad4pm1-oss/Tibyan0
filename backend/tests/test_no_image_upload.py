"""Screenshot verification has no server side: text is extracted in the visitor's browser and only the quote and
claim the visitor confirms reach the API, through the same /api/v1/analyze request as typed text.

These tests pin that down: no route accepts files or form data, images sent to the API are refused before any
processing, nothing is written to the temporary directory, and the analyze contract is unchanged.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def client(monkeypatch, synthetic_db):
    for k, v in {"DATABASE_PATH": str(synthetic_db), "EMBEDDING_PROVIDER": "hash", "EMBEDDING_MODEL": "",
                 "RATE_LIMIT_PER_MINUTE": "0"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_no_route_takes_files_or_form_data(client):
    app = client.app
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for p in route.dependant.body_params:
            info = p.field_info
            assert type(info).__name__ not in ("File", "Form"), f"{route.path} accepts {type(info).__name__}"
        assert "upload" not in route.path.lower() and "image" not in route.path.lower() and "ocr" not in route.path.lower()


@pytest.mark.parametrize("path", ["/api/v1/analyze", "/api/v1/upload", "/api/v1/ocr", "/upload"])
def test_image_posts_are_refused_and_nothing_is_written(client, path):
    before = set(Path(tempfile.gettempdir()).iterdir())
    small = client.post(path, files={"file": ("shot.png", PNG, "image/png")})
    raw = client.post(path, content=PNG, headers={"content-type": "image/png"})
    big = client.post(path, files={"file": ("shot.png", PNG + b"\x00" * 200_000, "image/png")})
    for r in (small, raw, big):
        assert r.status_code in (404, 405, 413, 415, 422), (path, r.status_code)
        assert r.headers["content-type"].startswith("application/json")
        assert "shot.png" not in r.text and "Traceback" not in r.text
    assert big.status_code in (404, 405, 413)          # large bodies are cut off by the body-size limit
    created = set(Path(tempfile.gettempdir()).iterdir()) - before
    assert not [p for p in created if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") or "shot" in p.name]


def test_text_confirmed_from_a_screenshot_is_an_ordinary_request(client):
    """The browser sends exactly {quote, claim, language}; the response is the usual one."""
    r = client.post("/api/v1/analyze", json={"quote": EXACT, "claim": "النص يذكر الملخص", "language": "ar"})
    assert r.status_code == 200
    body = r.json()
    assert body["quote_analysis"]["match_status"] == "EXACT"
    for key in ("input_source", "image", "ocr"):
        assert key not in body
