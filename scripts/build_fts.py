"""Build the FTS5/BM25 index (APPROVED sources only) and record the text integrity digest.

usage: python scripts/build_fts.py [--db PATH] [--test-fixture]
"""

import argparse
import sys
from pathlib import Path

from _common import DEFAULT_DB

from app.corpus.common import set_info
from app.corpus.fts import build_fts
from app.corpus.validation import original_text_digest
from app.db.connection import connect


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--test-fixture", action="store_true", help="allow synthetic fixture sources (test DBs only)")
    a = ap.parse_args()
    conn = connect(Path(a.db))
    n = build_fts(conn, production=not a.test_fixture)
    set_info(conn, "original_text_sha256", original_text_digest(conn))
    set_info(conn, "quran_original_text_sha256", original_text_digest(conn, "quran"))
    conn.commit()
    print(f"FTS5 indexes: {n} passages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
