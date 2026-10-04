"""Parse Sahih al-Bukhari and Sahih Muslim from OpenITI mARkdown files (Shamela editions).

Input files are acquired by scripts/fetch_hadith.py and accepted only if their SHA-256 equals the
pinned value in data/metadata/hadith_sahihayn_openiti.json. Nothing here invents, completes or
re-numbers hadith text: records are emitted only where the source file itself carries the number.

Transformations (documented in docs/DATA_PIPELINE.md §Hadith):
  T1  OpenITI markup removed: page markers (PageVxxPyyy, "### | [ص: n]"), milestones (msNNNN),
      line-continuation markers ("~~"), paragraph markers ("# "), stray HTML tags ("</span>").
  T2  Paragraph lines of one hadith are joined with a single space; separate narrations
      (Muslim: several "(N)" paragraphs with the same number) are joined with a newline.
  T3  Whitespace collapsed. No letter, diacritic or punctuation inside the text is changed.

Bukhari: a hadith starts at a heading "### | N - " (numbering of the Tawq al-Najat edition, which
follows Muhammad Fuad Abd al-Baqi). Lines "# N2 -" directly after the heading are extra numbers the
edition prints for the same text (numbers_covered). The block ends at the next heading other than
a page marker. Parsing starts at the heading of the first book («بدء الوحي»), after the editor's introduction.

Muslim: a narration starts at a paragraph "# (N) " (Abd al-Baqi numbering) and runs until the next
"(M)" paragraph or heading. Narrations sharing N form one record. Kitab al-Iman hadith 1-99 carry no
number in this file and are NOT ingested (documented gap), nor is the author's introduction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

_PAGE = re.compile(r"PageV\d+P\d+")
_MS = re.compile(r"\bms\d+\b")
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_WS = re.compile(r"\s+")

_B_HADITH = re.compile(r"^### \| (\d+)(?: ms\d+)? ?-\s*$")
_B_EXTRA_NUM = re.compile(r"^# (\d+) -\s*$")
_B_PAGE_HEAD = re.compile(r"^### \| \[ص: (?:ms\d+ )?\d+\]\s*$")
_B_START = "### | بدء الوحي"
_BOOK_HEAD = re.compile(r"^### \$ (\d+) -\s*(.*)$")
_M_BOOK_HEAD = re.compile(r"^### \| (\d+) - (كتاب.*)$")
_M_BAB_HEAD = re.compile(r"^### \|\| (\d+) - (.*)$")
_M_NARR = re.compile(r"^# \((\d+)\)\s?(.*)$")
# a "### $" heading that carries narration text (not just "### $ N -"): an UNNUMBERED narration
_M_UNNUM = re.compile(r"^### \$ (?!\s*\d+(?: ms\d+)? -\s*$)\s*(.+)$")
_ARABIC_WORD = re.compile(r"[\u0621-\u064a]{2,}")
_LEAD_DIGITS = re.compile(r"^\s*\d+\s*")


def clean(s: str) -> str:
    s = _PAGE.sub(" ", s)
    s = _MS.sub(" ", s)
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", s).strip()


@dataclass
class HadithRecord:
    number: int | None          # the edition's number; None for narrations the file does not number
    text: str
    book: str | None = None
    book_number: int | None = None
    chapter: str | None = None
    numbers_covered: list[int] = field(default_factory=list)
    narrations: int = 1
    source_line: int = 0          # 1-based line of the heading/marker in the raw file
    chapter_number: int | None = None
    ordinal: int | None = None    # unnumbered narrations: position among unnumbered narrations of the chapter


def _logical_lines(raw: str) -> list[tuple[int, str]]:
    """Join '~~' continuation lines onto their paragraph; keep 1-based start line numbers."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(raw.split("\n"), start=1):
        if line.startswith("~~") and out:
            n, prev = out[-1]
            out[-1] = (n, prev + " " + line[2:])
        else:
            out.append((i, line))
    return out


def parse_bukhari(raw: str) -> tuple[list[HadithRecord], dict]:
    lines = _logical_lines(raw)
    start = next(i for i, (_, s) in enumerate(lines) if s.startswith(_B_START))
    recs: list[HadithRecord] = []
    book = chapter = None
    book_no = None
    cur: HadithRecord | None = None
    parts: list[str] = []
    expect_extra = False
    pending_bab = False
    pending_book = False

    def close():
        nonlocal cur, parts
        if cur is not None:
            cur.text = clean(" ".join(parts))
            if cur.text:
                recs.append(cur)
        cur, parts = None, []

    for ln, s in lines[start:]:
        if _B_PAGE_HEAD.match(s) or re.fullmatch(r"#?\s*PageV\d+P\d+\s*", s.strip()):
            continue
        m = _B_HADITH.match(s)
        if m:
            close()
            cur = HadithRecord(number=int(m.group(1)), text="", book=book, book_number=book_no,
                               chapter=chapter, source_line=ln)
            cur.numbers_covered = [cur.number]
            expect_extra = True
            continue
        if s.startswith("###"):
            close()
            expect_extra = False
            bm = _BOOK_HEAD.match(s)
            if bm:
                book_no = int(bm.group(1))
                book = clean(bm.group(2)) or None
                pending_book = book is None
                chapter = None
                continue
            body = clean(s[3:].lstrip(" |$"))
            if body.startswith("باب"):
                chapter = body
                pending_bab = body in ("باب", "باب:")
            elif body and book is None:
                book = body          # first book of Bukhari has no numbered book heading in the file
            elif body:
                chapter = body if not body.startswith("[") else chapter
            continue
        if not s.startswith("#"):
            continue
        txt = s[1:].strip()
        if cur is not None:
            em = _B_EXTRA_NUM.match(s)
            if expect_extra and em:
                cur.numbers_covered.append(int(em.group(1)))
                continue
            expect_extra = False
            parts.append(txt)
            continue
        # text outside a numbered hadith: chapter titles continued on the next line, book titles,
        # chapter preambles (tarajim, mu'allaqat) -> metadata only, never ingested as hadith
        if pending_book and clean(txt).startswith("كتاب"):
            book = clean(txt)
            pending_book = False
        elif pending_bab and clean(txt):
            chapter = (chapter + " " + clean(txt)).strip()
            pending_bab = False
    close()
    nums = [r.number for r in recs]
    covered = {n for r in recs for n in r.numbers_covered}
    stats = {"records": len(recs), "min": min(nums), "max": max(nums),
             "duplicates": sorted({n for n in nums if nums.count(n) > 1}),
             "numbers_covered": len(covered),
             "gaps": [n for n in range(1, max(nums) + 1) if n not in covered]}
    return recs, stats


def parse_muslim(raw: str) -> tuple[list[HadithRecord], dict]:
    """Numbered narrations "(N)" are grouped by N. Narrations that start at a "### $ <text>" heading carry
    no number in the file: they are kept as UNNUMBERED records (number None) located by book, chapter and
    their ordinal among the chapter's unnumbered narrations. A bare digit sequence at the start of such a
    heading is an unmarked, inconsistently present edition marker: it is removed as markup and never used
    as a hadith number. Text before the first book (the author's introduction) is never ingested."""
    lines = _logical_lines(raw)
    recs: dict[object, HadithRecord] = {}
    order: list[object] = []
    book = chapter = None
    book_no = bab_no = None
    unnum_count: dict[tuple, int] = {}
    cur: object | None = None
    cur_parts: list[str] = []

    def flush():
        nonlocal cur, cur_parts
        if cur is not None:
            t = clean(" ".join(cur_parts))
            if t:
                r = recs[cur]
                r.text = (r.text + "\n" + t) if r.text else t
        cur, cur_parts = None, []

    for ln, s in lines:
        if s.startswith("###"):
            flush()
            bm = _M_BOOK_HEAD.match(s)
            if bm:
                book_no, book, chapter, bab_no = int(bm.group(1)), clean(bm.group(2)), None, None
                continue
            cm = _M_BAB_HEAD.match(s)
            if cm:
                bab_no, chapter = int(cm.group(1)), clean(cm.group(2))
                continue
            um = _M_UNNUM.match(s)
            if um and book is not None and bab_no is not None:
                k = unnum_count[(book_no, bab_no)] = unnum_count.get((book_no, bab_no), 0) + 1
                key = ("u", book_no, bab_no, k)
                recs[key] = HadithRecord(number=None, text="", book=book, book_number=book_no, chapter=chapter,
                                         chapter_number=bab_no, ordinal=k, source_line=ln, narrations=1)
                order.append(key)
                cur, cur_parts = key, [_LEAD_DIGITS.sub("", um.group(1))]
            continue
        if not s.startswith("#"):
            continue
        m = _M_NARR.match(s)
        if m:
            flush()
            n = int(m.group(1))
            if n not in recs:
                recs[n] = HadithRecord(number=n, text="", book=book, book_number=book_no, chapter=chapter,
                                       chapter_number=bab_no, source_line=ln, numbers_covered=[n], narrations=0)
                order.append(n)
            recs[n].narrations += 1
            cur, cur_parts = n, [m.group(2)]
            continue
        if cur is not None:
            cur_parts.append(s[1:].strip())
    flush()
    # an unnumbered "record" must contain real text (>= 3 Arabic words); stray markup headings such as
    # "### $ - 0" are dropped
    out = [recs[k] for k in order if recs[k].text and (
        recs[k].number is not None or len(_ARABIC_WORD.findall(recs[k].text)) >= 3)]
    numbered = [r for r in out if r.number is not None]
    nums = [r.number for r in numbered]
    stats = {"records": len(out), "numbered": len(numbered), "unnumbered": len(out) - len(numbered),
             "min": min(nums), "max": max(nums), "duplicates": [],
             "non_monotonic_numbers": sum(1 for a, b in pairwise(nums) if b < a),
             "numbers_covered": len(nums),
             "gaps": [n for n in range(1, max(nums) + 1) if n not in recs]}
    return out, stats
