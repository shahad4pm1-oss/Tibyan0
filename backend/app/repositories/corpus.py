"""Read-only access to the canonical corpus.

Every query that can feed a user-visible result joins `sources` and requires
verification_status = 'APPROVED' (defense in depth on top of the index build),
and excludes synthetic fixtures unless the corpus is a test fixture corpus.
"""

from __future__ import annotations

import json
import sqlite3

from app.services.types import Passage

_COLS = "p.id, p.rowid_int, p.source_id, p.reference, p.sequence, p.parent_id, p.original_text, " \
        "p.normalized_text, p.normalized_text_alt, p.metadata_json"


def _row(r: sqlite3.Row) -> Passage:
    return Passage(id=r[0], rowid=r[1], source_id=r[2], reference=r[3], sequence=r[4], parent_id=r[5],
                   original_text=r[6], normalized_text=r[7], normalized_text_alt=r[8],
                   metadata=json.loads(r[9]))


def fts_phrase(tokens: list[str]) -> str:
    return '"' + " ".join(t.replace('"', "") for t in tokens) + '"'


def fts_any(tokens: list[str]) -> str:
    uniq = list(dict.fromkeys(t.replace('"', "") for t in tokens if t))
    return " OR ".join(f'"{t}"' for t in uniq[:64])


_INDEXES = ("passages_fts", "hadith_fts")


class CorpusRepository:
    """`index` selects which FTS table bm25/phrase search use: 'passages_fts' (Quran, the default)
    or 'hadith_fts'. Lookups by id are index-independent."""

    def __init__(self, conn: sqlite3.Connection, index: str = "passages_fts"):
        if index not in _INDEXES:
            raise ValueError(f"unknown index {index!r}")
        self.index = index
        self.conn = conn
        info = {k: v for k, v in conn.execute("SELECT key, value FROM corpus_info")}
        self.info = info
        self.allow_synthetic = info.get("corpus_kind") == "test_fixture"
        self._eligible = (
            "s.verification_status = 'APPROVED' AND (s.source_type != 'synthetic_fixture' OR "
            + ("1" if self.allow_synthetic else "0") + ")"
        )

    # ---- lookups
    def source(self, source_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(r) if r else None

    def get(self, passage_id: str) -> Passage | None:
        r = self.conn.execute(
            f"SELECT {_COLS} FROM passages p JOIN sources s ON s.id = p.source_id "
            f"WHERE p.id = ? AND {self._eligible}", (passage_id,)).fetchone()
        return _row(r) if r else None

    def by_rowids(self, rowids: list[int]) -> dict[int, Passage]:
        if not rowids:
            return {}
        q = ",".join("?" * len(rowids))
        rows = self.conn.execute(
            f"SELECT {_COLS} FROM passages p JOIN sources s ON s.id = p.source_id "
            f"WHERE p.rowid_int IN ({q}) AND {self._eligible}", rowids).fetchall()
        return {r[1]: _row(r) for r in rows}

    def neighbor(self, passage_id: str, relation: str) -> Passage | None:
        r = self.conn.execute(
            "SELECT related_passage_id FROM context_links WHERE passage_id = ? AND relation_type = ?",
            (passage_id, relation)).fetchone()
        return self.get(r[0]) if r else None

    def for_index(self, index: str) -> CorpusRepository:
        """Same connection, different search index."""
        return CorpusRepository(self.conn, index)

    def count_by_type(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.conn.execute(
            f"SELECT s.source_type, count(*) FROM passages p JOIN sources s ON s.id = p.source_id "
            f"WHERE {self._eligible} GROUP BY s.source_type")}

    def count_eligible(self) -> int:
        return self.conn.execute(
            f"SELECT count(*) FROM passages p JOIN sources s ON s.id = p.source_id WHERE {self._eligible}"
        ).fetchone()[0]

    # ---- search
    def bm25(self, tokens: list[str], k: int) -> list[tuple[Passage, float]]:
        if not tokens:
            return []
        rows = self.conn.execute(
            f"""SELECT {_COLS}, bm25({self.index}) AS score
                FROM {self.index} JOIN passages p ON p.rowid_int = {self.index}.rowid
                JOIN sources s ON s.id = p.source_id
                WHERE {self.index} MATCH ? AND {self._eligible}
                ORDER BY score LIMIT ?""", (fts_any(tokens), k)).fetchall()
        return [(_row(r), r[10]) for r in rows]

    def phrase_hits(self, tokens: list[str], limit: int = 200) -> list[Passage]:
        if not tokens:
            return []
        rows = self.conn.execute(
            f"""SELECT {_COLS} FROM {self.index} JOIN passages p ON p.rowid_int = {self.index}.rowid
                JOIN sources s ON s.id = p.source_id
                WHERE {self.index} MATCH ? AND {self._eligible}
                ORDER BY p.source_id, p.sequence LIMIT ?""", (fts_phrase(tokens), limit)).fetchall()
        return [_row(r) for r in rows]
