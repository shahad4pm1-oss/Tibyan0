"""Deterministic quote comparison (no LLM): the user's quote against the canonical source text.

Purpose: show WHAT differs between the submitted quote and the approved text, token by token, in neutral terms.
It never changes matching, attribution, thresholds or the gate: it runs after the existing pipeline has decided,
on the passages that pipeline returned.

Canonical text is never modified. All comparison happens on a separate comparison representation:
  - user tokens: NFKC + norm-v1 per whitespace token (search normalization, comparison only)
  - Quran: two comparison columns, as in the matcher: the publisher's imla'i text (KFGQPC aya_text_emlaey) and
    the Uthmani text, both under norm-v1; the column that aligns better with the quote is used. Imla'i tokens are
    mapped back onto the displayed Uthmani tokens by a character-level alignment, so the display stays Uthmani.
  - hadith: NFKC + norm-v1 per token of the stored text; honorific formulas (the hnorm-v1 list) are compared as
    normalization-only differences, never as missing or substituted words.

Token statuses (user side / canonical side):
  MATCHED                 identical
  NORMALIZATION_ONLY      equal after search normalization; reasons: diacritics, tatweel, punctuation, alef_forms,
                          presentation_forms, honorific, orthography (Uthmani vs imla'i spelling)
  SUBSTITUTED             a different word at the same place
  DELETED_FROM_USER_QUOTE canonical word inside the quoted range that the quote does not contain
  ADDED_BY_USER           quote word that is not in the canonical text
  OUTSIDE_QUOTE           canonical word before/after the quoted range (the quote is part of a longer text)
  IGNORED                 token with no letters (symbols, ayah/pause marks, separated punctuation)

`definitive` is True only for a resolved source (EXACT/PARTIAL). Comparisons against candidates of an
AMBIGUOUS result are returned separately and are never definitive.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.services.normalizer import _DIACRITICS, _HON_SEQS, _TATWEEL, normalize_for_search  # comparison only
from app.services.types import Passage

VERSION = "diff-v1"

MATCHED = "MATCHED"
NORMALIZATION_ONLY = "NORMALIZATION_ONLY"
SUBSTITUTED = "SUBSTITUTED"
DELETED = "DELETED_FROM_USER_QUOTE"
ADDED = "ADDED_BY_USER"
OUTSIDE = "OUTSIDE_QUOTE"
IGNORED = "IGNORED"

_PRIORITY = {SUBSTITUTED: 6, DELETED: 5, ADDED: 5, NORMALIZATION_ONLY: 3, MATCHED: 2, OUTSIDE: 1, IGNORED: 0}
_ALEF_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})


def _cmp_tokens(raw: str) -> list[str]:
    return normalize_for_search(unicodedata.normalize("NFKC", raw)).split()


def _diacritics(s: str) -> str:
    return "".join(_DIACRITICS.findall(s))


def _punct(s: str) -> list[str]:
    return [ch for ch in s if unicodedata.category(ch)[0] in "PS"]


def _letters(s: str) -> str:
    s = s.replace(_TATWEEL, "")
    s = _DIACRITICS.sub("", s)
    return "".join(ch for ch in s if unicodedata.category(ch)[0] not in "PS")


def norm_reasons(a: str, b: str) -> list[str]:
    """Why two raw tokens that are equal under search normalization are not identical. Deterministic."""
    a, b = unicodedata.normalize("NFC", a), unicodedata.normalize("NFC", b)   # code-point order only
    if a == b:
        return []
    r: list[str] = []
    if unicodedata.normalize("NFKC", a) != a or unicodedata.normalize("NFKC", b) != b:
        r.append("presentation_forms")
        a, b = unicodedata.normalize("NFKC", a), unicodedata.normalize("NFKC", b)
    if a.count(_TATWEEL) != b.count(_TATWEEL):
        r.append("tatweel")
    if _diacritics(a) != _diacritics(b):
        r.append("diacritics")
    if _punct(a) != _punct(b):
        r.append("punctuation")
    la, lb = _letters(a), _letters(b)
    if la != lb and la.translate(_ALEF_FOLD) == lb.translate(_ALEF_FOLD):
        r.append("alef_forms")
    elif la != lb:
        r.append("orthography")
    return r or ["formatting"]


@dataclass
class _Seq:
    """A comparison sequence: normalized tokens, each owned by one display token."""
    toks: list[str] = field(default_factory=list)
    owner: list[list[int]] = field(default_factory=list)  # display-token indices (usually one)
    raw_form: list[str] = field(default_factory=list)    # raw comparison form of the owning token (for reasons)


def _honorific_mask(toks: list[str]) -> list[bool]:
    mask = [False] * len(toks)
    i = 0
    while i < len(toks):
        for seq in _HON_SEQS:
            if tuple(toks[i:i + len(seq)]) == seq:
                for k in range(i, i + len(seq)):
                    mask[k] = True
                i += len(seq)
                break
        else:
            i += 1
    return mask


def _char_owner_map(src_tokens: list[str], dst_tokens: list[str]) -> list[list[int]]:
    """For each dst token, the src token indices it overlaps after a character-level alignment of the
    concatenated (normalized) token streams. Used to map imla'i comparison tokens onto Uthmani display tokens."""
    a_chars, a_own = [], []
    for i, t in enumerate(src_tokens):
        for ch in t:
            a_chars.append(ch)
            a_own.append(i)
    b_chars, b_own = [], []
    for j, t in enumerate(dst_tokens):
        for ch in t:
            b_chars.append(ch)
            b_own.append(j)
    out: list[set[int]] = [set() for _ in dst_tokens]
    sm = SequenceMatcher(None, a_chars, b_chars, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            continue
        if tag == "delete":
            continue
        for k in range(j2 - j1):
            ai = i1 + min(k * (i2 - i1) // max(j2 - j1, 1), i2 - i1 - 1)
            out[b_own[j1 + k]].add(a_own[ai])
    # tokens left unmapped (pure insertions) take their nearest mapped neighbour
    for j in range(len(out)):
        if not out[j]:
            near = next((out[k] for d in range(1, len(out)) for k in (j - d, j + d) if 0 <= k < len(out) and out[k]),
                        {0})
            out[j] = set(near)
    return [sorted(s) for s in out]


@dataclass
class _Canon:
    display: list[str]          # displayed canonical tokens (never altered)
    passage_of: list[str]       # passage id per display token
    columns: list[tuple[str, _Seq]]  # (basis name, comparison sequence)


def _canonical(passages: list[Passage], source_type: str) -> _Canon:
    display: list[str] = []
    passage_of: list[str] = []
    uth = _Seq()
    imla = _Seq()
    imla_ok = source_type == "quran"
    for p in passages:
        base = len(display)
        raw = p.original_text.split()
        display.extend(raw)
        passage_of.extend([p.id] * len(raw))
        for i, t in enumerate(raw):
            for sub in _cmp_tokens(t):
                uth.toks.append(sub)
                uth.owner.append([base + i])
                uth.raw_form.append(t)
        if imla_ok:
            em = (p.metadata or {}).get("publisher_aya_text_emlaey")
            if not em:
                imla_ok = False
                continue
            em_raw = em.split()
            norm_disp = ["".join(_cmp_tokens(t)) for t in raw]
            norm_em = ["".join(_cmp_tokens(t)) for t in em_raw]
            owners = _char_owner_map(norm_disp, norm_em)
            for j, t in enumerate(em_raw):
                for sub in _cmp_tokens(t):
                    imla.toks.append(sub)
                    imla.owner.append([base + o for o in owners[j]])
                    imla.raw_form.append(t)
    cols = []
    if imla_ok:
        cols.append(("imlaei", imla))
    cols.append(("canonical", uth))
    return _Canon(display, passage_of, cols)


def _user(quote: str) -> tuple[list[str], _Seq]:
    raw = quote.split()
    s = _Seq()
    for i, t in enumerate(raw):
        for sub in _cmp_tokens(t):
            s.toks.append(sub)
            s.owner.append([i])
            s.raw_form.append(t)
    return raw, s


def _equal_count(u: list[str], c: list[str]) -> int:
    return sum(b.size for b in SequenceMatcher(None, u, c, autojunk=False).get_matching_blocks())


def compare(quote: str, passages: list[Passage], source_type: str, definitive: bool) -> dict | None:
    """Compare the user's quote with the canonical text of `passages`. Returns a JSON-ready dict or None."""
    if not passages or not quote.strip():
        return None
    hadith = source_type == "hadith"
    u_raw, us = _user(quote)
    canon = _canonical(passages, source_type)
    if not us.toks:
        return None

    u_hon = _honorific_mask(us.toks) if hadith else [False] * len(us.toks)
    best = None
    for basis, cs in canon.columns:
        c_hon = _honorific_mask(cs.toks) if hadith else [False] * len(cs.toks)
        u_idx = [k for k in range(len(us.toks)) if not u_hon[k]]
        c_idx = [k for k in range(len(cs.toks)) if not c_hon[k]]
        score = _equal_count([us.toks[k] for k in u_idx], [cs.toks[k] for k in c_idx])
        if best is None or score > best[0]:
            best = (score, basis, cs, c_hon, u_idx, c_idx)
    _, basis, cs, c_hon, u_idx, c_idx = best

    u_stat: list[tuple[str, list[str]]] = [("", [])] * len(us.toks)
    c_stat: list[tuple[str, list[str]]] = [("", [])] * len(cs.toks)
    pairs: list[dict] = []
    ut = [us.toks[k] for k in u_idx]
    ct_all = [cs.toks[k] for k in c_idx]
    # local alignment: anchor on the longest common run, compare against a window of the canonical text around
    # it (long hadith texts would otherwise attract stray one-word matches far away). Outside the window: context.
    m = SequenceMatcher(None, ut, ct_all, autojunk=False).find_longest_match(0, len(ut), 0, len(ct_all))
    slack = max(3, len(ut) // 2)
    w_lo, w_hi = (max(0, m.b - m.a - slack), min(len(ct_all), m.b + (len(ut) - m.a) + slack)) if m.size else (0, len(ct_all))
    for k in c_idx[:w_lo] + c_idx[w_hi:]:
        c_stat[k] = (OUTSIDE, [])
    c_win = c_idx[w_lo:w_hi]
    sm = SequenceMatcher(None, ut, [cs.toks[k] for k in c_win], autojunk=False)
    ops = sm.get_opcodes()
    eq = [n for n, op in enumerate(ops) if op[0] == "equal"]
    first_eq, last_eq = (eq[0], eq[-1]) if eq else (len(ops), -1)

    def similar(a: int, b: int) -> bool:
        return SequenceMatcher(None, us.toks[a], cs.toks[b], autojunk=False).ratio() >= 0.5

    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        uu = [u_idx[k] for k in range(i1, i2)]
        cc = [c_win[k] for k in range(j1, j2)]
        edge = n < first_eq or n > last_eq
        if tag == "equal":
            for a, b in zip(uu, cc, strict=True):
                rs = norm_reasons(us.raw_form[a], cs.raw_form[b])
                st = NORMALIZATION_ONLY if rs else MATCHED
                u_stat[a] = (st, rs)
                c_stat[b] = (st, rs)
        elif tag == "delete":        # quote tokens absent from the canonical text
            for a in uu:
                u_stat[a] = (ADDED, [])
            pairs.append({"kind": ADDED, "user": " ".join(dict.fromkeys(us.raw_form[a] for a in uu)), "canonical": None})
        elif tag == "insert":        # canonical tokens absent from the quote
            for b in cc:
                c_stat[b] = (OUTSIDE if edge else DELETED, [])
            if not edge:
                pairs.append({"kind": DELETED, "user": None,
                              "canonical": " ".join(dict.fromkeys(cs.raw_form[b] for b in cc))})
        else:  # replace
            if edge and not (len(uu) == len(cc) and all(similar(a, b) for a, b in zip(uu, cc, strict=True))):
                # quote starts/ends with words that are not in the text: added words; the text there is context
                for a in uu:
                    u_stat[a] = (ADDED, [])
                for b in cc:
                    c_stat[b] = (OUTSIDE, [])
                pairs.append({"kind": ADDED, "user": " ".join(dict.fromkeys(us.raw_form[a] for a in uu)),
                              "canonical": None})
                continue
            for a, b in zip(uu, cc, strict=False):
                u_stat[a] = (SUBSTITUTED, [])
                c_stat[b] = (SUBSTITUTED, [])
            for a in uu[len(cc):]:
                u_stat[a] = (ADDED, [])
            for b in cc[len(uu):]:
                c_stat[b] = (DELETED, [])
            pairs.append({"kind": SUBSTITUTED, "user": " ".join(dict.fromkeys(us.raw_form[a] for a in uu)),
                          "canonical": " ".join(dict.fromkeys(cs.raw_form[b] for b in cc))})

    # honorific formulas: never missing/substituted words; normalization-only inside the quoted range
    quoted_c = [b for b in range(len(cs.toks)) if c_stat[b][0] in (MATCHED, NORMALIZATION_ONLY, SUBSTITUTED, DELETED)]
    lo, hi = (min(quoted_c), max(quoted_c)) if quoted_c else (len(cs.toks), -1)
    for b in range(len(cs.toks)):
        if c_hon[b]:
            c_stat[b] = (NORMALIZATION_ONLY, ["honorific"]) if lo < b < hi else (OUTSIDE, [])
    for a in range(len(us.toks)):
        if u_hon[a]:
            u_stat[a] = (NORMALIZATION_ONLY, ["honorific"])

    # aggregate to display tokens
    def agg(n_display: int, owners: list[int], stats: list[tuple[str, list[str]]]):
        out = [(IGNORED, set()) for _ in range(n_display)]
        for k, owns in enumerate(owners):
            st, rs = stats[k]
            if not st:
                continue
            for own in owns:
                cur, crs = out[own]
                if _PRIORITY[st] > _PRIORITY[cur]:
                    out[own] = (st, set(rs))
                elif st == cur:
                    crs.update(rs)
        return out

    u_disp = agg(len(u_raw), us.owner, u_stat)
    c_disp = agg(len(canon.display), cs.owner, c_stat)
    # display tokens without letters inside the quoted range stay IGNORED; outside the range they are context
    quoted_d = [i for i, (st, _) in enumerate(c_disp) if st not in (OUTSIDE, IGNORED)]
    dlo, dhi = (min(quoted_d), max(quoted_d)) if quoted_d else (0, -1)
    for i, (st, rs) in enumerate(c_disp):
        if st == IGNORED and not (dlo <= i <= dhi):
            c_disp[i] = (OUTSIDE, rs)

    counts = {k: 0 for k in (SUBSTITUTED, DELETED, ADDED, NORMALIZATION_ONLY, OUTSIDE)}
    for st, _ in c_disp:
        if st in counts and st != ADDED:
            counts[st] += 1
    counts[ADDED] = sum(1 for st, _ in u_disp if st == ADDED)
    reasons = sorted({r for _, rs in u_disp for r in rs} | {r for _, rs in c_disp for r in rs})
    summary = []
    if counts[SUBSTITUTED]:
        summary.append({"code": "SUBSTITUTED_WORDS", "count": counts[SUBSTITUTED]})
    if counts[DELETED]:
        summary.append({"code": "MISSING_WORDS", "count": counts[DELETED]})
    if counts[ADDED]:
        summary.append({"code": "ADDED_WORDS", "count": counts[ADDED]})
    if counts[OUTSIDE] and quoted_d:
        summary.append({"code": "PARTIAL_QUOTE", "count": counts[OUTSIDE]})
    if not (counts[SUBSTITUTED] or counts[DELETED] or counts[ADDED]):
        summary.append({"code": "NORMALIZATION_ONLY", "reasons": reasons} if reasons else {"code": "VERBATIM"})

    return {
        "version": VERSION,
        "definitive": definitive,
        "source_type": source_type,
        "passage_ids": [p.id for p in passages],
        "basis": basis,
        "summary": summary,
        "user_tokens": [{"text": t, "status": st, "reasons": sorted(rs)} for t, (st, rs) in zip(u_raw, u_disp, strict=True)],
        "canonical_tokens": [{"text": t, "status": st, "reasons": sorted(rs), "passage_id": pid}
                             for t, (st, rs), pid in zip(canon.display, c_disp, canon.passage_of, strict=True)],
        "differences": pairs[:40],   # substantive differences only, in reading order
        "quoted_range": [dlo, dhi] if quoted_d else None,
    }
