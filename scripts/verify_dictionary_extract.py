"""Verify the curated terminology entries against the official Scientific Package (page 8).

Checks for every entry and field:
  1. the corrected text differs from the PDF text layer ONLY by the documented text-layer defect
     (lam-alif ligatures stored as reversed pairs; whitespace around punctuation; mark placement):
     strip(defect(corrected)) == strip(text_layer)
  2. if data/raw/package/scientific_package_v1448-3-20.pdf exists (SHA-256 pinned in the JSON), each
     text_layer string occurs in a fresh `pdftotext -f 8 -l 8` extraction of that file.
Exit code 1 on any mismatch.

usage: python scripts/verify_dictionary_extract.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys

from _common import ROOT
from fetch_quran import sha256

CUR = ROOT / "data/curated/dictionary_scientific_package_p8.json"
PDF = ROOT / "data/raw/package/scientific_package_v1448-3-20.pdf"
_DEFECT = {"لا": "ال", "لأ": "أل", "لإ": "إل", "لآ": "آل"}
_STRIP = re.compile("[\\s\u064b-\u0652\u202a-\u202e\u200e\u200f]")


def defect(s: str) -> str:
    return re.sub("ل[اأإآ]", lambda m: _DEFECT[m.group(0)], s)


def strip(s: str) -> str:
    return _STRIP.sub("", s)


def main() -> int:
    doc = json.loads(CUR.read_text(encoding="utf-8"))
    bad = 0
    for e in doc["entries"]:
        for f in ("term_ar", "translation", "usage_note_ar"):
            if strip(defect(e[f])) != strip(e["text_layer"][f]):
                print(f"MISMATCH {e['id']} {f}")
                bad += 1
    print(f"rule check: {len(doc['entries'])} entries, {bad} mismatches")
    if PDF.exists() and shutil.which("pdftotext"):
        if sha256(PDF) != doc["package_file"]["sha256"]:
            print("package PDF present but sha256 differs from the pinned value")
            return 1
        txt = subprocess.run(["pdftotext", "-f", "8", "-l", "8", str(PDF), "-"], capture_output=True,
                             text=True, check=True).stdout
        flat = strip(txt)
        miss = [(e["id"], f) for e in doc["entries"] for f in ("term_ar", "translation", "usage_note_ar")
                if strip(e["text_layer"][f]) not in flat]
        for m in miss:
            print(f"NOT IN PDF TEXT LAYER {m}")
        bad += len(miss)
        print(f"pdf check: package sha256 verified, {len(miss)} missing")
    else:
        print("pdf check skipped: package PDF not present locally")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
