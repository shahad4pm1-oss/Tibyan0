"""Validate the corpus DB. Exit code 1 on any failure.

usage: python scripts/validate_corpus.py [--db PATH] [--test-fixture]
"""

import argparse
import json
import sys
from pathlib import Path

from _common import DEFAULT_DB, META_DIR

from app.corpus.validation import validate
from app.db.connection import connect


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--test-fixture", action="store_true")
    a = ap.parse_args()
    if not Path(a.db).exists():
        print(f"FAIL: database not found: {a.db}")
        return 1
    conn = connect(Path(a.db), readonly=True)
    rep = validate(conn, production=not a.test_fixture,
                   structure_expected=META_DIR / "quran_structure_expected.json")
    # The Quran text must stay exactly as built in Phase 2 (pinned digest of id + original_text).
    if not a.test_fixture:
        pinned = json.loads((META_DIR / "quran_kfgqpc_hafs_v2.json").read_text(encoding="utf-8")) \
            .get("original_text_digest_pinned")
        from app.corpus.validation import original_text_digest
        if pinned and original_text_digest(conn, "quran") != pinned:
            rep.errors.append("V13: Quran original_text digest differs from the pinned Phase 2 digest")
    print(json.dumps({"ok": rep.ok, "checks": rep.checks_run, "stats": rep.stats,
                      "errors": rep.errors}, ensure_ascii=False, indent=1))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
