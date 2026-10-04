from fastapi.testclient import TestClient

from app.main import app


def test_health_fields():
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert {"status", "app_env", "corpus_version", "pipeline_version", "corpus_available", "search_mode",
            "embedding_model"} <= set(body)
    assert body["corpus_available"] == (body["status"] == "ok")
