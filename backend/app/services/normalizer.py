"""Arabic search normalization (SEARCH-ONLY).

The output of this module is used to build and query search indexes. It is never
stored as, or displayed as, religious text. Canonical `original_text` is never
passed through it for storage.

Rules (version norm-v1), applied in this order:
  R1 Unicode NFC
  R2 remove tatweel (U+0640)
  R3 remove Arabic diacritics and Quranic annotation marks:
       U+0610-U+061A, U+064B-U+065F, U+0670 (superscript alef),
       U+06D6-U+06DC, U+06DF-U+06E8, U+06EA-U+06ED, U+08D3-U+08FF
  R4 replace with a space: Quranic section/sajdah symbols U+06DE (۞) U+06E9 (۩);
     Arabic punctuation U+060C (،) U+061B (؛) U+061F (؟) U+06D4 (۔) U+066A-U+066D;
     ornate parentheses U+FD3E/U+FD3F (﴾ ﴿); quotation marks « » “ ” ‘ ’ " ';
     ASCII punctuation; digits (ASCII, Arabic-Indic U+0660-U+0669, Extended U+06F0-U+06F9)
     (users paste quotes with brackets and ayah numbers; none of these are letters)
  R5 alef normalization: أ (U+0623), إ (U+0625), آ (U+0622), ٱ (U+0671) -> ا (U+0627)
  R6 whitespace: all Unicode whitespace incl. NBSP -> single space; strip ends

Deliberately NOT applied (see docs/METHODOLOGY.md): ة->ه, ى->ي, ؤ/ئ->ء,
hamza seat folding, Latin/digit changes. These need evaluation evidence first.
"""

from __future__ import annotations

import re
import unicodedata

VERSION = "norm-v1"

_TATWEEL = "ـ"
_DIACRITICS = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ࣓-ࣿ]"
)
_SYMBOLS = re.compile(
    "[۞۩،؛؟۔٪-٭﴾﴿«»“”‘’"
    "0-9٠-٩۰-۹"
    + re.escape("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
    + "]"
)
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
_WS = re.compile(r"\s+", flags=re.UNICODE)


def normalize_for_search(text: str) -> str:
    t = unicodedata.normalize("NFC", text)  # R1
    t = t.replace(_TATWEEL, "")  # R2
    t = _DIACRITICS.sub("", t)  # R3
    t = _SYMBOLS.sub(" ", t)  # R4
    t = t.translate(_ALEF)  # R5
    t = _WS.sub(" ", t.replace(" ", " ")).strip()  # R6
    return t


def tokens(text: str) -> list[str]:
    """Normalize then split on spaces."""
    n = normalize_for_search(text)
    return n.split(" ") if n else []


# ---------------------------------------------------------------------------------------------
# Hadith search normalization (SEARCH-ONLY), version hnorm-v1. Used ONLY for the hadith index and
# for queries against it; the Quran index and its queries keep norm-v1 unchanged.
#   H1 Unicode NFKC: expands presentation forms and ligatures such as ﷺ (U+FDFA) -> صلى الله عليه وسلم
#      and Arabic presentation forms (U+FB50-U+FDFF, U+FE70-U+FEFF) -> base letters
#   H2 norm-v1 (diacritics, tatweel, punctuation, decorative symbols, alef forms, whitespace)
#   H3 remove honorific formulas as whole-token sequences (both in the text and in the query), so a
#      quote typed with ﷺ, with the formula written out, or without it searches the same text:
#      صلى الله عليه (وآله|واله)? وسلم; (رضي|رضى) الله (عنه|عنها|عنهما|عنهم|عنهن);
#      عليه/عليها/عليهم (الصلاة و)?السلام
# The stored/displayed original_text is never changed.
HADITH_VERSION = "hnorm-v1"
_HONORIFICS = [
    "صلى الله عليه وسلم", "صلى الله عليه واله وسلم", "صلى الله عليه وآله وسلم",
    "رضي الله عنه", "رضي الله عنها", "رضي الله عنهما", "رضي الله عنهم", "رضي الله عنهن",
    "رضى الله عنه", "رضى الله عنها", "رضى الله عنهما", "رضى الله عنهم", "رضى الله عنهن",
    "عليه الصلاة والسلام", "عليه السلام", "عليها السلام", "عليهم السلام",
]
_HON_SEQS = sorted({tuple(normalize_for_search(h).split()) for h in _HONORIFICS}, key=len, reverse=True)


def normalize_hadith_search(text: str) -> str:
    toks = normalize_for_search(unicodedata.normalize("NFKC", text)).split()   # H1 + H2
    out: list[str] = []
    i = 0
    while i < len(toks):                                                       # H3
        for seq in _HON_SEQS:
            if tuple(toks[i:i + len(seq)]) == seq:
                i += len(seq)
                break
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def hadith_tokens(text: str) -> list[str]:
    n = normalize_hadith_search(text)
    return n.split(" ") if n else []


def nfkc_tokens(text: str) -> list[str]:
    """norm-v1 after NFKC (expands ﷺ and presentation forms) WITHOUT removing honorifics: matches the
    plain norm-v1 search copy of hadith text, for quotes cut in the middle of an honorific formula."""
    return tokens(unicodedata.normalize("NFKC", text))
