"""Terminology entries from the official Scientific Package (p.8)."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.corpus.validation import validate
from app.db.connection import connect
from app.services.terminology import Terminology

ROOT = Path(__file__).resolve().parents[2]


def test_curated_entries_differ_from_pdf_text_layer_only_by_documented_defect():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/verify_dictionary_extract.py")],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout
    assert "10 entries, 0 mismatches" in r.stdout


@pytest.mark.real_corpus
def test_terms_ingested_and_not_indexed_as_passages(real_repo):
    c = real_repo.conn
    assert c.execute("SELECT count(*) FROM terms").fetchone()[0] == 10
    assert c.execute("SELECT source_type FROM sources WHERE id='glossary:scientific-package-samples'").fetchone()[0] \
        == "dictionary"
    # terms are not passages: never a candidate source for a quote
    assert c.execute("SELECT count(*) FROM passages WHERE source_id='glossary:scientific-package-samples'").fetchone()[0] == 0
    row = c.execute("SELECT translation, usage_note FROM terms WHERE id='glossary:sp:en:tawhid'").fetchone()
    assert row[0] == "Tawhid / Oneness of God" and row[1].startswith("يفضل إبقاء المصطلح")


@pytest.mark.real_corpus
def test_lookup_exact_with_proclitics_only(real_repo):
    t = Terminology(real_repo.conn)
    ids = lambda s: {e["id"] for e in t.lookup(s)}
    assert ids("ترجم كلمة التوحيد إلى الإنجليزية") == {"glossary:sp:en:tawhid"}
    assert "glossary:sp:en:islam" in ids("هذا من أصول الإسلام وللإسلام")
    assert ids("الموحدون") == set()                  # no stemming / fuzzy matching
    assert ids("السماء صافية اليوم") == set()


@pytest.mark.real_corpus
def test_pending_dictionary_source_fails_validation(real_db, tmp_path):
    dst = tmp_path / "c.sqlite3"
    shutil.copy(real_db, dst)
    c = connect(dst)
    c.execute("UPDATE sources SET verification_status='PENDING_REVIEW' WHERE id='glossary:scientific-package-samples'")
    c.commit()
    rep = validate(c, production=True)
    assert any(e.startswith("V16") for e in rep.errors) and any(e.startswith("V01") for e in rep.errors)
    assert Terminology(c).lookup("التوحيد") == []     # pending entries are never served


@pytest.mark.real_corpus
def test_glossary_is_named_as_package_samples_not_jamhara(real_repo):
    s = real_repo.source("glossary:scientific-package-samples")
    assert s["source_type"] == "dictionary"
    assert s["title"].startswith("Official Scientific Package Sample Glossary") and "Jamhara" not in s["title"]
    meta = __import__("json").loads(s["metadata_json"])
    assert meta["records"] == 10 and "NOT the Jamhara dictionary" in meta["scope_note"]
