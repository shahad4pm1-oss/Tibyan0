"""Create a fresh corpus DB and ingest the verified KFGQPC Hafs package.

usage: python scripts/ingest_quran.py [--db PATH] [--corpus-version V]
"""

import argparse
import sys

from _common import DEFAULT_DB, META_DIR, ROOT

from app.corpus.common import set_info
from app.corpus.quran import ingest
from app.db.connection import connect, init_schema


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--corpus-version", default="c1-kfgqpc-hafs-2.0u13")
    a = ap.parse_args()

    from pathlib import Path
    db = Path(a.db)
    if db.exists():
        db.unlink()
    conn = connect(db)
    init_schema(conn)
    n = ingest(conn, META_DIR / "quran_kfgqpc_hafs_v2.json", ROOT, a.corpus_version)
    set_info(conn, "corpus_kind", "production")
    set_info(conn, "corpus_version", a.corpus_version)
    conn.commit()
    print(f"ingested {n} Quran passages into {db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
