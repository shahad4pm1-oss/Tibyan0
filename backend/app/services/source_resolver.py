"""Source resolution: RESOLVED / AMBIGUOUS / NOT_FOUND.

Uses only verified corpus data and deterministic retrieval/matching results. No LLM.
A source is RESOLVED only if every matched passage re-reads from the corpus with an
APPROVED source and identical original_text (guards against stale objects).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.repositories.corpus import CorpusRepository
from app.services.types import MatchStatus, Passage, QuoteMatch, ResolutionStatus


@dataclass
class Resolution:
    status: ResolutionStatus
    passages: list[Passage] = field(default_factory=list)
    source: dict | None = None
    alternatives: list[Passage] = field(default_factory=list)
    alternatives_total: int = 0
    reason: str = ""


class SourceResolver:
    def __init__(self, repo: CorpusRepository):
        self.repo = repo

    def resolve(self, match: QuoteMatch) -> Resolution:
        if match.status is MatchStatus.NOT_FOUND:
            return Resolution(ResolutionStatus.NOT_FOUND, reason="no matching passage in the approved corpus")
        if match.status is MatchStatus.AMBIGUOUS:
            return Resolution(ResolutionStatus.AMBIGUOUS, alternatives=match.alternatives,
                              alternatives_total=match.alternatives_total,
                              reason="the quote matches more than one passage")
        verified: list[Passage] = []
        for p in match.passages:
            fresh = self.repo.get(p.id)
            if fresh is None or fresh.original_text != p.original_text:
                return Resolution(ResolutionStatus.NOT_FOUND, reason=f"passage {p.id} failed re-verification")
            verified.append(fresh)
        src_ids = {p.source_id for p in verified}
        if len(src_ids) != 1:
            return Resolution(ResolutionStatus.AMBIGUOUS, alternatives=verified, reason="span crosses sources")
        src = self.repo.source(src_ids.pop())
        if not src or src["verification_status"] != "APPROVED":
            return Resolution(ResolutionStatus.NOT_FOUND, reason="source not APPROVED")
        return Resolution(ResolutionStatus.RESOLVED, passages=verified, source=src)
