"""Ingest a hadith collection in Tibyan's canonical JSONL format into an existing DB.

No real Bukhari/Muslim dataset is cleared yet (REAL_HADITH = BLOCKED_BY_DATA).
Only synthetic NON-RELIGIOUS fixtures have been ingested with this script.

usage: python scripts/ingest_hadith.py --manifest M.json --input H.jsonl [--db PATH]
"""

import argparse
import sys
from pathlib import Path

from _common import DEFAULT_DB

from app.corpus.hadith import ingest
from app.db.connection import connect


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--corpus-version", required=True)
    a = ap.parse_args()
    conn = connect(Path(a.db))
    n = ingest(conn, Path(a.manifest), Path(a.input), a.corpus_version)
    conn.commit()
    print(f"ingested {n} hadith passages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
