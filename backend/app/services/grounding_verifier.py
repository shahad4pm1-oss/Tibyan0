"""Grounding verifier: the AI's free text may not carry religious text that is not in the cited evidence.

Checks on summary, reason, relevance notes and uncertainty_reason:
  UNSUPPORTED_QUOTATION      a quoted segment («…» “…” "…" ﴿…﴾) of >= 2 words that is not contained in a
                             CITED evidence passage (either search copy) nor in the user's own quote/claim
  UNSUPPORTED_SCRIPTURE      any 5-word window that occurs in the Quran or hadith corpus only at passages NOT
                             supplied as evidence (the model reproduced another ayah or hadith from memory)
  SCRIPTURE_FORMATTED_TEXT   Uthmani-script characters (alef wasla, small high/low marks) in AI text; AI text
                             must never look like scripture
Display rule enforced elsewhere: every religious text shown to users comes from backend evidence items;
the AI text is displayed only inside the labelled AI-analysis block.
"""

from __future__ import annotations

import re

from app.repositories.corpus import CorpusRepository
from app.schemas.claim_analysis import LLMClaimOutput
from app.services.evidence_builder import Evidence
from app.services.normalizer import normalize_for_search, tokens

_QUOTED = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"|﴿([^﴾]+)﴾|﴾([^﴿]+)﴿")
_UTHMANI = re.compile("[ٱۖ-ࣰۭ-ࣲ]")
WINDOW = 5


def _texts(o: LLMClaimOutput) -> list[str]:
    return ([o.summary, o.reason, o.uncertainty_reason or ""] + [k.relevance for k in o.key_evidence]
            + [a.claim_part for a in o.assertions])


class GroundingVerifier:
    def __init__(self, repo: CorpusRepository):
        self.repo = repo
        # every passage index is checked: Quran (default) and hadith
        self.search_repos = [repo] + [repo.for_index(ix) for ix in ("hadith_fts",) if ix != repo.index]

    def verify(self, o: LLMClaimOutput, evidence: list[Evidence], quote: str, claim: str) -> list[str]:
        issues: list[str] = []
        by_id = {e.id: e for e in evidence}
        cited_pids = {by_id[i].passage_id for i in o.evidence_ids if i in by_id and by_id[i].passage_id}
        supplied_pids = {e.passage_id for e in evidence if e.passage_id}
        cited_hay = []
        for pid in cited_pids:
            p = self.repo.get(pid)
            if p:
                cited_hay += [p.normalized_text, p.normalized_text_alt or ""]
        # a cited tafsir item holds both labelled layers (verse + commentary), so its text is citable
        cited_hay += [normalize_for_search(by_id[i].text) for i in o.evidence_ids
                      if i in by_id and by_id[i].role == "source_commentary"]
        user_hay = [normalize_for_search(quote), normalize_for_search(claim)]

        for text in _texts(o):
            if _UTHMANI.search(text):
                issues.append("SCRIPTURE_FORMATTED_TEXT")
            for m in _QUOTED.finditer(text):
                seg = normalize_for_search(next(g for g in m.groups() if g))
                if len(seg.split()) < 2:
                    continue
                if not any(seg in h for h in cited_hay + user_hay if h):
                    issues.append("UNSUPPORTED_QUOTATION")
            toks = tokens(text)
            for i in range(max(0, len(toks) - WINDOW + 1)):
                # a window is unsupported only if it occurs in some index and NONE of its occurrences
                # (Quran or hadith) is a supplied evidence passage: hadith often quote ayat verbatim
                hit_ids = {h.id for r in self.search_repos for h in r.phrase_hits(toks[i:i + WINDOW], limit=50)}
                if hit_ids and not (hit_ids & supplied_pids):
                    issues.append("UNSUPPORTED_SCRIPTURE")
                    break
        return sorted(set(issues))
