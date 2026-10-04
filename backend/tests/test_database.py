import sqlite3

import pytest

from app.db.connection import connect, init_schema


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite3")
    init_schema(c)
    return c


def test_tables_exist(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"sources", "passages", "context_links", "corpus_info", "passages_fts"} <= names


def test_required_columns(conn):
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    assert {"id", "source_type", "title", "author", "edition", "publisher", "source_url", "license_note",
            "verification_status", "acquired_at", "corpus_version", "metadata_json"} <= cols("sources")
    assert {"id", "source_id", "reference", "sequence", "parent_id", "original_text", "normalized_text",
            "metadata_json"} <= cols("passages")
    assert {"id", "passage_id", "related_passage_id", "relation_type", "priority"} <= cols("context_links")


def test_indexes_exist(conn):
    idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_passages_source_seq", "idx_passages_parent", "idx_context_passage"} <= idx


def _source(conn, sid="s", status="APPROVED"):
    conn.execute("INSERT INTO sources (id, source_type, title, edition, license_note, verification_status, "
                 "acquired_at, corpus_version) VALUES (?, 'synthetic_fixture', 't', 'e', 'l', ?, 'd', 'v')",
                 (sid, status))


def test_foreign_key_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO passages (id, rowid_int, source_id, reference, sequence, original_text, "
                     "normalized_text) VALUES ('x', 1, 'missing', 'r', 1, 'نص', 'نص')")


def test_status_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _source(conn, status="MAYBE")


def test_empty_text_rejected(conn):
    _source(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO passages (id, rowid_int, source_id, reference, sequence, original_text, "
                     "normalized_text) VALUES ('x', 1, 's', 'r', 1, '   ', 'نص')")


def test_duplicate_passage_id_rejected(conn):
    _source(conn)
    q = ("INSERT INTO passages (id, rowid_int, source_id, reference, sequence, original_text, normalized_text) "
         "VALUES ('x', ?, 's', 'r', ?, 'نص', 'نص')")
    conn.execute(q, (1, 1))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(q, (2, 2))


def test_context_link_must_resolve(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO context_links (passage_id, related_passage_id, relation_type) "
                     "VALUES ('a', 'b', 'next')")


@pytest.mark.real_corpus
def test_real_corpus_shape(real_repo):
    c = real_repo.conn
    assert c.execute("SELECT count(*) FROM passages WHERE source_id = 'quran'").fetchone()[0] == 6236
    assert c.execute("SELECT count(DISTINCT parent_id) FROM passages WHERE source_id = 'quran'").fetchone()[0] == 114
    assert c.execute("SELECT verification_status FROM sources WHERE id='quran'").fetchone()[0] == "APPROVED"
