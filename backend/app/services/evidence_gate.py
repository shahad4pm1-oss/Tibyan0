"""Evidence sufficiency gate. Runs BEFORE the LLM; the LLM is called only on PASS.

Decisions: PASS / INSUFFICIENT / SPECIALIST_REQUIRED.
Evidence strength (no numeric confidence): SUFFICIENT / LIMITED / INSUFFICIENT, derived only from the
explicit conditions listed in `strength()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.services.content_level_router import Level
from app.services.evidence_builder import Evidence
from app.services.source_resolver import Resolution
from app.services.types import AmbiguityReason, MatchStatus, QuoteMatch, ResolutionStatus

ANALYSIS_SOURCE_TYPES = {"quran", "synthetic_fixture"}
NOT_ENABLED = "CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE"


class GateDecision(str, Enum):
    PASS = "PASS"
    INSUFFICIENT = "INSUFFICIENT"
    SPECIALIST_REQUIRED = "SPECIALIST_REQUIRED"


class Strength(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    LIMITED = "LIMITED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class GateResult:
    decision: GateDecision
    reasons: list[str] = field(default_factory=list)
    strength: Strength = Strength.INSUFFICIENT


def strength(res: Resolution, match: QuoteMatch, evidence: list[Evidence], integrity_ok: bool,
             quote_tokens: int, min_tokens_sufficient: int) -> Strength:
    """INSUFFICIENT: no resolved APPROVED source, no matched evidence, or integrity failure.
    LIMITED: resolved, but the quote is a short fragment (< min_tokens_sufficient normalized tokens).
    SUFFICIENT: resolved EXACT/PARTIAL match of >= min_tokens_sufficient tokens with matched evidence."""
    if (res.status is not ResolutionStatus.RESOLVED or not integrity_ok
            or match.status not in (MatchStatus.EXACT, MatchStatus.PARTIAL)
            or not any(e.role == "matched_source" for e in evidence)):
        return Strength.INSUFFICIENT
    if quote_tokens < min_tokens_sufficient:
        return Strength.LIMITED
    return Strength.SUFFICIENT


def evaluate(level: Level, res: Resolution, match: QuoteMatch, evidence: list[Evidence],
             context_matched: int, integrity_ok: bool, quote_tokens: int, min_quote_tokens: int,
             min_tokens_sufficient: int) -> GateResult:
    st = strength(res, match, evidence, integrity_ok, quote_tokens, min_tokens_sufficient)
    if level is Level.D:
        return GateResult(GateDecision.SPECIALIST_REQUIRED, ["PERSONAL_CASE_LEVEL_D"], st)

    reasons: list[str] = []
    if res.status is ResolutionStatus.NOT_FOUND:
        reasons.append("SOURCE_NOT_FOUND")
    if res.status is ResolutionStatus.AMBIGUOUS:
        reasons.append("SOURCE_AMBIGUOUS")
    if match.reason is AmbiguityReason.NEAR_MATCH_UNCONFIRMED:
        reasons.append("NEAR_MATCH_UNCONFIRMED")
    if match.status not in (MatchStatus.EXACT, MatchStatus.PARTIAL):
        reasons.append("NO_DIRECT_TEXTUAL_MATCH")
    if res.status is ResolutionStatus.RESOLVED:
        if not res.source or res.source.get("verification_status") != "APPROVED":
            reasons.append("SOURCE_NOT_APPROVED")
        if not any(e.role == "matched_source" for e in evidence):
            reasons.append("NO_EVIDENCE")
        if context_matched == 0:
            reasons.append("NO_CONTEXT")
        if not integrity_ok:
            reasons.append("INTEGRITY_CHECK_FAILED")
        if quote_tokens < min_quote_tokens:
            reasons.append("QUOTE_TOO_SHORT_FOR_ANALYSIS")
        # Claim analysis is enabled (and prompt-tested) for Quran evidence only. Hadith and any other
        # source type are shown with their text and metadata but never sent to the model (yet).
        if res.source and res.source.get("source_type") not in ANALYSIS_SOURCE_TYPES:
            reasons.append(NOT_ENABLED)
    if reasons:
        return GateResult(GateDecision.INSUFFICIENT, reasons, st)
    return GateResult(GateDecision.PASS, [], st)
