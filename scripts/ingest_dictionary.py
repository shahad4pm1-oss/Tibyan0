"""Ingest the terminology entries of the official Scientific Package (p.8) after verifying them.

usage: python scripts/ingest_dictionary.py [--db PATH]
"""

import argparse
import subprocess
import sys
from pathlib import Path

from _common import DEFAULT_DB, ROOT

from app.corpus.dictionary import ingest
from app.db.connection import connect


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    a = ap.parse_args()
    chk = subprocess.run([sys.executable, str(ROOT / "scripts/verify_dictionary_extract.py")], check=False)
    if chk.returncode != 0:
        print("dictionary verification failed; not ingesting")
        return 1
    conn = connect(Path(a.db))
    n = ingest(conn, ROOT / "data/curated/dictionary_scientific_package_p8.json", "sp-dict-1448")
    conn.commit()
    print(f"ingested {n} terminology entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
