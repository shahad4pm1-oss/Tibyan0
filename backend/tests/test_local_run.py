"""Local-run consolidation: .env location, empty optional values, Windows-safe DB paths, health fields."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import Settings, get_settings
from app.db.connection import connect
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_env_file_is_resolved_from_repo_root_not_cwd():
    code = ("import os; os.environ['TIBYAN_ENV_FILE_PROBE']='1'; from app.core import config; "
            "print(config._ENV_FILE)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", capture_output=True, text=True,
                         env={"PATH": "", "PYTHONPATH": str(ROOT / "backend"),
                              # Windows cannot start Python (socket provider) without SYSTEMROOT
                              **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {})},
                         check=True).stdout.strip()
    assert Path(out) == ROOT / ".env"
    assert config.REPO_ROOT == ROOT


def test_env_example_with_empty_optional_values_loads(tmp_path):
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert s.llm_provider is None and s.llm_api_key is None and s.llm_temperature is None
    assert s.cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]


@pytest.mark.parametrize("folder", ["with space", "مجلد عربي", "a#b"])
def test_readonly_connect_handles_spaces_and_non_ascii_paths(tmp_path, folder, synthetic_db):
    d = tmp_path / folder
    d.mkdir()
    shutil.copy(synthetic_db, d / "x.sqlite3")
    c = connect(d / "x.sqlite3", readonly=True)
    assert c.execute("SELECT count(*) FROM passages").fetchone()[0] > 0


@pytest.mark.real_corpus
def test_health_reports_components_version_and_llm_mode(monkeypatch, real_db):
    monkeypatch.setenv("DATABASE_PATH", str(real_db))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_lsa")
    monkeypatch.setenv("EMBEDDING_MODEL", "char-ngram-lsa-v1")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        h = c.get("/health").json()
    get_settings.cache_clear()
    assert h["status"] == "ok" and h["llm_mode"] == "LLM_UNAVAILABLE" and h["app_version"]
    comp = h["components"]
    assert comp["quran_corpus"]["passages"] == 6236 and comp["quran_corpus"]["ready"]
    assert comp["hadith_corpus"]["by_collection"] == {"hadith:bukhari": 7380, "hadith:muslim": 3114}
    assert comp["hadith_corpus"]["status"] == "LIMITED_PRODUCTION"
    assert "glossary" not in comp
    assert comp["lexical_search"]["indexes"] == {"passages_fts": 6236, "hadith_fts": 10494}
    assert comp["semantic_index"]["ready"] is True
