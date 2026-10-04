"""Deterministic quote matching. No LLM.

Order of rules (first that applies wins):

1. PHRASE  The quote's normalized tokens occur contiguously inside one passage
   (FTS5 phrase query over either search column, whole corpus, APPROVED only).
     - one hit                       -> EXACT if the tokens equal the whole passage, else PARTIAL
     - several hits, exactly one equals a whole passage -> EXACT on that one
     - otherwise several hits        -> AMBIGUOUS (alternatives listed)
     - quote shorter than MIN_PARTIAL_TOKENS and not a whole passage -> AMBIGUOUS/NOT_FOUND
2. SPAN    The tokens occur contiguously across 2..MAX_SPAN consecutive passages of the same
   parent (e.g. ayat of one surah), checked around the top retrieval candidates.
     -> EXACT if they equal the whole span, else PARTIAL; matched passages = the span
3. NEAR MATCH  Token coverage = |longest common token alignment| / |quote tokens| (difflib), best
   over the retrieval candidates and their spans. Retrieval scores (BM25 or semantic) are never
   used for this decision; candidates only define where to look.
     - coverage < PARAPHRASE_MIN_COVERAGE                      -> NOT_FOUND
     - PARAPHRASE_MODE = "disabled" (DEFAULT, required in production):
           any near match                                     -> AMBIGUOUS, reason NEAR_MATCH_UNCONFIRMED,
                                                                 closest passages listed, nothing attributed
     - PARAPHRASE_MODE = "experimental" (non-production only):
           margin to next different passage >= PARAPHRASE_MIN_MARGIN -> PARAPHRASED
           otherwise                                          -> AMBIGUOUS
PARAPHRASED is RESERVED/EXPERIMENTAL: true paraphrase retrieval is not validated and the thresholds
are not calibrated (docs/METHODOLOGY.md, docs/LIMITATIONS.md).
"""

from __future__ import annotations

from difflib import SequenceMatcher

from app.repositories.corpus import CorpusRepository
from app.services.normalizer import tokens
from app.services.types import AmbiguityReason, Candidate, MatchStatus, Passage, QuoteMatch


def _cols(p: Passage) -> list[list[str]]:
    out = [p.normalized_text.split(" ")]
    if p.normalized_text_alt:
        out.append(p.normalized_text_alt.split(" "))
    return out


def _contains(hay: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def _dedupe(ps: list[Passage]) -> list[Passage]:
    seen: set[str] = set()
    return [p for p in ps if not (p.id in seen or seen.add(p.id))]


def coverage(q: list[str], hay: list[str]) -> float:
    if not q:
        return 0.0
    sm = SequenceMatcher(None, q, hay, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(q)


class QuoteMatcher:
    def __init__(self, repo: CorpusRepository, min_partial_tokens: int = 2, max_span: int = 3,
                 min_coverage: float = 0.6, min_margin: float = 0.1, max_alternatives: int = 10,
                 paraphrase_mode: str = "disabled", fuzzy_min_tokens: int = 3, tokenize=tokens,
                 alt_tokenize=None):
        if paraphrase_mode not in ("disabled", "experimental"):
            raise ValueError(f"unknown paraphrase_mode {paraphrase_mode!r}")
        self.repo = repo
        self.paraphrase_mode = paraphrase_mode
        self.min_partial = min_partial_tokens
        self.max_span = max_span
        self.min_cov = min_coverage
        self.min_margin = min_margin
        self.max_alt = max_alternatives
        self.fuzzy_min_tokens = fuzzy_min_tokens
        self.tokenize = tokenize      # must match the normalization of the index this matcher searches
        # optional second tokenizer matching the index's second search column (hadith: the plain norm-v1
        # copy). A verbatim phrase found with EITHER normalization counts; nothing else is loosened.
        self.alt_tokenize = alt_tokenize

    # -- helpers
    def _span(self, p: Passage, before: int, after: int) -> list[Passage]:
        seq = [p]
        cur = p
        for _ in range(before):
            cur = self.repo.neighbor(cur.id, "previous")
            if not cur:
                break
            seq.insert(0, cur)
        cur = p
        for _ in range(after):
            cur = self.repo.neighbor(cur.id, "next")
            if not cur:
                break
            seq.append(cur)
        return seq

    def _windows(self, p: Passage) -> list[list[Passage]]:
        """All windows of 2..max_span consecutive passages that include p."""
        if self.max_span < 2 or p.parent_id is None:
            return []
        around = self._span(p, self.max_span - 1, self.max_span - 1)
        i = next(j for j, x in enumerate(around) if x.id == p.id)
        wins = []
        for size in range(2, self.max_span + 1):
            for start in range(max(0, i - size + 1), min(i, len(around) - size) + 1):
                wins.append(around[start:start + size])
        return wins

    @staticmethod
    def _joined(win: list[Passage]) -> list[list[str]]:
        cols = []
        for c in range(2):
            parts = [(_cols(x)[c] if len(_cols(x)) > c else None) for x in win]
            if all(pt is not None for pt in parts):
                cols.append([t for pt in parts for t in pt])
        return cols

    def _span_by_phrase(self, q: list[str]) -> dict[tuple[str, ...], tuple[list[Passage], bool]]:
        """Find q split across consecutive passages, anchored on a passage boundary.

        For each split point, the longer side is phrase-searched over the whole eligible corpus;
        hits must END with the left side (or START with the right side); the remainder must then
        be covered by the following (or preceding) passage(s), up to max_span passages in total.
        """
        found: dict[tuple[str, ...], tuple[list[Passage], bool]] = {}
        if self.max_span < 2 or len(q) < 2:
            return found
        for i in range(1, len(q)):
            left, right = q[:i], q[i:]
            anchor_left = len(left) >= len(right)
            anchor = left if anchor_left else right
            for p in self.repo.phrase_hits(anchor, limit=300):
                if p.parent_id is None:
                    continue
                for ci, col in enumerate(_cols(p)):
                    if anchor_left and col[-len(left):] != left:
                        continue
                    if not anchor_left and col[: len(right)] != right:
                        continue
                    win = [p]
                    rest = list(right if anchor_left else left)
                    cur = p
                    ok = False
                    while len(win) < self.max_span:
                        cur = self.repo.neighbor(cur.id, "next" if anchor_left else "previous")
                        if cur is None:
                            break
                        cc = _cols(cur)
                        if ci >= len(cc):
                            break
                        ct = cc[ci]
                        if anchor_left:
                            win.append(cur)
                            if len(rest) <= len(ct):
                                ok = ct[: len(rest)] == rest
                                whole_end = len(rest) == len(ct)
                                break
                            if ct != rest[: len(ct)]:
                                break
                            rest = rest[len(ct):]
                        else:
                            win.insert(0, cur)
                            if len(rest) <= len(ct):
                                ok = ct[-len(rest):] == rest
                                whole_end = len(rest) == len(ct)
                                break
                            if ct != rest[-len(ct):]:
                                break
                            rest = rest[: -len(ct)]
                    if ok:
                        joined = [t for x in win for t in (_cols(x)[ci] if ci < len(_cols(x)) else [])]
                        found[tuple(x.id for x in win)] = (win, joined == q and whole_end)
        return found

    # -- main
    def match(self, quote: str, candidates: list[Candidate]) -> QuoteMatch:
        q = self.tokenize(quote)
        if not q:
            return QuoteMatch(status=MatchStatus.NOT_FOUND, method="none")

        # 1. PHRASE over the whole eligible corpus
        qs = [q]
        if self.alt_tokenize is not None:
            q2 = self.alt_tokenize(quote)
            if q2 and q2 != q:
                qs.append(q2)
        hits = _dedupe([h for qq in qs for h in self.repo.phrase_hits(qq)])
        if hits:
            whole = [h for h in hits if any(col == qq for col in _cols(h) for qq in qs)]
            if len(hits) == 1:
                st = MatchStatus.EXACT if whole else MatchStatus.PARTIAL
                if st is MatchStatus.PARTIAL and len(q) < self.min_partial:
                    return QuoteMatch(status=MatchStatus.AMBIGUOUS, method="phrase", alternatives=hits,
                                      alternatives_total=1, coverage=1.0, reason=AmbiguityReason.QUOTE_TOO_SHORT)
                return QuoteMatch(status=st, method="phrase", passages=hits, coverage=1.0)
            if len(whole) == 1:
                return QuoteMatch(status=MatchStatus.EXACT, method="phrase", passages=whole, coverage=1.0)
            alts = whole if len(whole) > 1 else hits
            return QuoteMatch(status=MatchStatus.AMBIGUOUS, method="phrase", coverage=1.0,
                              alternatives=alts[: self.max_alt], alternatives_total=len(alts),
                              reason=AmbiguityReason.MULTIPLE_LOCATIONS)

        # 2. SPAN across consecutive passages: (a) boundary-anchored phrase search over the whole
        #    corpus (independent of ranking), then (b) windows around the top candidates.
        span_hits: dict[tuple[str, ...], tuple[list[Passage], bool]] = self._span_by_phrase(q)
        for c in candidates:
            for win in self._windows(c.passage):
                for col in self._joined(win):
                    if _contains(col, q):
                        key = tuple(x.id for x in win)
                        span_hits[key] = (win, col == q)
        if span_hits:
            # keep minimal spans (drop windows that strictly contain another hit)
            keys = sorted(span_hits, key=len)
            minimal = [k for k in keys if not any(set(o) < set(k) for o in keys if o != k)]
            if len(minimal) == 1:
                win, whole = span_hits[minimal[0]]
                return QuoteMatch(status=MatchStatus.EXACT if whole else MatchStatus.PARTIAL, method="span",
                                  passages=win, coverage=1.0)
            alts = _dedupe([span_hits[k][0][0] for k in minimal])
            return QuoteMatch(status=MatchStatus.AMBIGUOUS, method="span", coverage=1.0,
                              alternatives=alts[: self.max_alt], alternatives_total=len(minimal),
                              reason=AmbiguityReason.MULTIPLE_LOCATIONS)

        # 3. FUZZY token coverage
        if len(q) < self.fuzzy_min_tokens:
            return QuoteMatch(status=MatchStatus.NOT_FOUND, method="none")
        scored: list[tuple[float, list[Passage]]] = []
        for c in candidates:
            options = [[c.passage]] + self._windows(c.passage)
            best = (0.0, [c.passage])
            for win in options:
                for col in self._joined(win) if len(win) > 1 else _cols(c.passage):
                    cv = coverage(q, col)
                    # prefer the shorter window on ties
                    if cv > best[0] + 1e-9:
                        best = (cv, win)
            scored.append(best)
        if not scored:
            return QuoteMatch(status=MatchStatus.NOT_FOUND, method="none")
        scored.sort(key=lambda t: -t[0])
        top_cov, top_win = scored[0]
        top_ids = {x.id for x in top_win}
        runner = next((cv for cv, w in scored[1:] if not ({x.id for x in w} & top_ids)), 0.0)
        if top_cov < self.min_cov:
            return QuoteMatch(status=MatchStatus.NOT_FOUND, method="fuzzy", coverage=top_cov)
        near = _dedupe([p for cv, w in scored if cv >= self.min_cov for p in w])
        if self.paraphrase_mode == "disabled" or top_cov - runner < self.min_margin:
            # Conservative: a non-exact match is never attributed. Closest passages are listed only.
            return QuoteMatch(status=MatchStatus.AMBIGUOUS, method="near_match", coverage=top_cov,
                              alternatives=near[: self.max_alt], alternatives_total=len(near),
                              reason=AmbiguityReason.NEAR_MATCH_UNCONFIRMED)
        return QuoteMatch(status=MatchStatus.PARAPHRASED, method="near_match_experimental", passages=top_win,
                          coverage=top_cov)
