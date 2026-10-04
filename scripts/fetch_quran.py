"""Acquire the KFGQPC Uthmanic Hafs data package and verify it byte-for-byte.

No Quran text is typed or generated here: the file is downloaded and accepted
only if its SHA-256 equals the pinned digest, which matches the MD5/SHA-1
published by KFGQPC (see data/metadata/quran_kfgqpc_hafs_v2.json).

Sources are tried in order; all must yield identical bytes.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data" / "metadata" / "quran_kfgqpc_hafs_v2.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    meta = json.loads(META.read_text(encoding="utf-8"))
    pkg = meta["package"]
    dest = ROOT / pkg["local_path"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and sha256(dest) == pkg["sha256"]:
        print(f"already present and verified: {dest.relative_to(ROOT)}")
        return 0

    for url in pkg["acquisition_urls"]:
        tmp = dest.with_suffix(".part")
        try:
            print(f"trying {url}")
            with urllib.request.urlopen(url, timeout=60) as r, tmp.open("wb") as out:
                out.write(r.read())
        except (urllib.error.URLError, OSError, TimeoutError) as e:  # network policy, geo-restriction
            print(f"  failed: {type(e).__name__}: {e}")
            tmp.unlink(missing_ok=True)
            continue
        digest = sha256(tmp)
        if digest != pkg["sha256"]:
            print(f"  REJECTED: sha256 {digest} != pinned {pkg['sha256']}")
            tmp.unlink(missing_ok=True)
            continue
        tmp.replace(dest)
        print(f"  verified sha256 {digest} -> {dest.relative_to(ROOT)}")
        return 0

    print("ERROR: could not obtain a verified copy from any source", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
