"""Acquire the Sahih al-Bukhari and Sahih Muslim source files (OpenITI, Shamela editions).

No hadith text is typed or generated: each file is downloaded from the pinned repository commit and
accepted only if its SHA-256 equals the value in data/metadata/hadith_sahihayn_openiti.json.

usage: python scripts/fetch_hadith.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from _common import META_DIR, ROOT
from fetch_quran import sha256

META = META_DIR / "hadith_sahihayn_openiti.json"


def main() -> int:
    meta = json.loads(META.read_text(encoding="utf-8"))
    for col in meta["collections"]:
        f = col["file"]
        dest = ROOT / f["local_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and sha256(dest) == f["sha256"]:
            print(f"already present and verified: {dest.relative_to(ROOT)}")
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            print(f"trying {f['url']}")
            with urllib.request.urlopen(f["url"], timeout=120) as r, tmp.open("wb") as out:
                out.write(r.read())
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            tmp.unlink(missing_ok=True)
            print(f"ERROR: {col['source_id']}: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        digest = sha256(tmp)
        if digest != f["sha256"] or tmp.stat().st_size != f["size_bytes"]:
            tmp.unlink(missing_ok=True)
            print(f"ERROR: {col['source_id']}: REJECTED sha256 {digest} != pinned {f['sha256']}", file=sys.stderr)
            return 1
        tmp.replace(dest)
        print(f"  verified sha256 {digest} -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
