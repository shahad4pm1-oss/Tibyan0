"""Normalization never modifies stored or displayed original_text."""

import zipfile

import pytest

from app.corpus.quran import split_publisher_text
from app.corpus.validation import original_text_digest
from app.db.connection import connect
from app.repositories.corpus import CorpusRepository
from app.services.lexical_retriever import LexicalRetriever
from app.services.normalizer import normalize_for_search
from app.services.quote_matcher import QuoteMatcher


def test_synthetic_queries_do_not_change_stored_text(synthetic_db):
    repo = CorpusRepository(connect(synthetic_db, readonly=True))
    before = original_text_digest(repo.conn)
    for q in ("قَرَأَ كِتَابًا", "الى البيت", "لعب الاطفال"):
        QuoteMatcher(repo).match(q, LexicalRetriever(repo).search(q))
    assert original_text_digest(repo.conn) == before == repo.info["original_text_sha256"]


def test_displayed_text_keeps_diacritics(synthetic_repo):
    p = synthetic_repo.get("synth:1:1")
    assert p.original_text != normalize_for_search(p.original_text)
    assert "َ" in p.original_text  # fatha preserved in canonical text


def test_split_publisher_text_is_reversible():
    o, sep, mark = split_publisher_text("كلمة كلمة ﰀ")
    assert o + sep + mark == "كلمة كلمة ﰀ" and o == "كلمة كلمة"


@pytest.mark.real_corpus
def test_real_original_equals_publisher_text_minus_mark(real_repo):
    """Every stored ayah equals the publisher's aya_text with only the ayah-number glyph removed."""
    import csv
    import io
    import json
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    meta = json.loads((root / "data/metadata/quran_kfgqpc_hafs_v2.json").read_text(encoding="utf-8"))
    raw = zipfile.ZipFile(root / meta["package"]["local_path"]).read(meta["package"]["member_used"]).decode("utf-8-sig")
    rows = {f"quran:{r['sura_no']}:{r['aya_no']}": r["aya_text"] for r in csv.DictReader(io.StringIO(raw))}
    n = 0
    for pid, txt in real_repo.conn.execute("SELECT id, original_text FROM passages WHERE source_id = 'quran'"):
        pub = rows[pid]
        assert pub.startswith(txt)
        assert len(pub) - len(txt) == 2  # separator + one glyph, nothing else
        n += 1
    assert n == 6236


@pytest.mark.real_corpus
def test_real_digest_matches_build(real_repo):
    assert original_text_digest(real_repo.conn) == real_repo.info["original_text_sha256"]
