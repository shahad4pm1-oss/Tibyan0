"""Ingest Sahih al-Bukhari and Sahih Muslim (verified OpenITI/Shamela files) into an existing corpus DB.

Run after scripts/ingest_quran.py and scripts/fetch_hadith.py. Quran rows are not touched.
usage: python scripts/ingest_sahihayn.py [--db PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from _common import DEFAULT_DB, META_DIR, ROOT

from app.corpus.common import set_info
from app.corpus.sahihayn import ingest
from app.db.connection import connect

CORPUS_VERSION = "c2-quran-hafs2.0u13+sahihayn-openiti-44e1c36+sp-dict-1448"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    a = ap.parse_args()
    conn = connect(Path(a.db))
    stats = ingest(conn, META_DIR / "hadith_sahihayn_openiti.json", ROOT, "hadith-openiti-44e1c36")
    set_info(conn, "corpus_version", CORPUS_VERSION)
    conn.commit()
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
