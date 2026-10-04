from __future__ import annotations

import sqlite3

# source group -> FTS table. Separate tables keep each corpus's BM25 statistics independent.
INDEX_FOR_TYPE = {"quran": "passages_fts", "synthetic_fixture": "passages_fts", "hadith": "hadith_fts"}
INDEXES = ("passages_fts", "hadith_fts")


def build_fts(conn: sqlite3.Connection, production: bool) -> int:
    """(Re)build the FTS5 indexes from APPROVED sources only.

    In production, synthetic fixture sources are never indexed even if marked APPROVED.
    Source types without an index (e.g. dictionary) are never indexed as passages.
    """
    total = 0
    for table in INDEXES:
        types = [t for t, ix in INDEX_FOR_TYPE.items() if ix == table]
        conn.execute(f"DELETE FROM {table}")
        conn.execute(
            f"""INSERT INTO {table} (rowid, normalized_text, normalized_text_alt)
               SELECT p.rowid_int, p.normalized_text, COALESCE(p.normalized_text_alt, '')
               FROM passages p JOIN sources s ON s.id = p.source_id
               WHERE s.verification_status = 'APPROVED'
                 AND s.source_type IN ({",".join("?" * len(types))})
                 AND (s.source_type != 'synthetic_fixture' OR ? = 0)""",
            (*types, 1 if production else 0),
        )
        total += conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    conn.commit()
    return total
