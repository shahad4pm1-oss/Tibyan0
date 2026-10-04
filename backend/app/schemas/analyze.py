"""API contracts for POST /api/v1/analyze (Phase 3).

All religious text in a response comes from backend evidence (context / evidence.items). The only
model-written text is in claim_analysis (summary, reason, key_evidence[].relevance, uncertainty_reason),
labelled by claim_analysis.summary_source and displayed as AI analysis, never as source text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

_ARABIC_LETTER = range(0x0621, 0x064B)


class AnalyzeRequest(BaseModel):
    quote: str = Field(min_length=2, max_length=2000)
    claim: str = Field(min_length=2, max_length=2000)
    language: Literal["ar"] = "ar"

    @field_validator("quote")
    @classmethod
    def _quote_has_arabic(cls, v: str) -> str:
        if not any(ord(ch) in _ARABIC_LETTER or 0x0671 <= ord(ch) <= 0x06D3 for ch in v):
            raise ValueError("quote must contain Arabic text")
        return v


class TextUnit(BaseModel):
    passage_id: str
    reference: str
    text: str  # canonical original_text; never normalized text
    metadata: dict = {}
    source_type: str | None = None   # quran | hadith | ...


class QuoteAnalysis(BaseModel):
    match_status: Literal["EXACT", "PARTIAL", "PARAPHRASED", "AMBIGUOUS", "NOT_FOUND"]
    matched_text: str | None
    match_method: str
    token_coverage: float | None = None
    alternatives: list[TextUnit] = []
    alternatives_total: int = 0
    ambiguity_reason: Literal["MULTIPLE_LOCATIONS", "NEAR_MATCH_UNCONFIRMED", "QUOTE_TOO_SHORT"] | None = None


class SourceInfo(BaseModel):
    source_id: str
    title: str
    reference: str
    source_url: str | None
    edition: str
    publisher: str | None
    source_type: str = "quran"
    author: str | None = None
    verification_status: str = "APPROVED"


class Context(BaseModel):
    kind: str = "retrieved_context_window"
    before: list[TextUnit] = []
    matched: list[TextUnit] = []
    after: list[TextUnit] = []
    supporting_material: list[dict] = []


class EvidenceItemOut(BaseModel):
    id: str
    passage_id: str | None
    source_id: str
    reference: str | None
    text: str
    role: str
    source_title: str | None = None
    edition: str | None = None
    metadata: dict | None = None
    source_type: str | None = None
    verification_status: str | None = None


class EvidenceOut(BaseModel):
    strength: Literal["SUFFICIENT", "LIMITED", "INSUFFICIENT"] = "INSUFFICIENT"
    items: list[EvidenceItemOut] = []


class ClaimOut(BaseModel):
    text: str


class KeyEvidenceOut(BaseModel):
    evidence_id: str
    relevance: str  # AI-written note (labelled as AI analysis)


class GateOut(BaseModel):
    decision: Literal["PASS", "INSUFFICIENT", "SPECIALIST_REQUIRED"]
    reasons: list[str] = []


class AssertionOut(BaseModel):
    claim_part: str
    evidence_context: str
    label: Literal["supported", "overstated", "contradicted", "not_in_evidence", "requires_specialist"]


class ClaimAnalysis(BaseModel):
    status: Literal["COMPLETED", "ABSTAINED", "REFERRED", "ANALYSIS_UNAVAILABLE", "AI_OUTPUT_REJECTED"]
    relation: Literal["SUPPORTED", "OVERSTATED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE",
                      "REQUIRES_SPECIALIST"] | None
    summary: str | None
    summary_source: Literal["ai", "system_template"] | None
    reason: str | None = None
    evidence_ids: list[str] = []
    key_evidence: list[KeyEvidenceOut] = []
    needs_specialist: bool = False
    uncertainty_reason: str | None = None
    referral: str | None = None
    content_level: Literal["A", "B", "C", "D"]
    level_policy: Literal["ANALYZE", "SCOPED", "BLOCKED"] | None = None
    level_scope: list[str] = []
    verdict: Literal["correct", "manipulated", "unrelated"] | None = None
    assertions: list[AssertionOut] = []
    level_rules: list[str] = []
    gate: GateOut
    safety_overrides: list[str] = []
    attempts: int = 0
    disclosure: str


class Warning_(BaseModel):
    code: str
    message: str


class Metadata(BaseModel):
    corpus_version: str
    retrieval_version: str
    pipeline_version: str
    normalizer_version: str
    embedding_model: str | None
    search_mode: Literal["HYBRID", "LEXICAL_ONLY"]
    ranking_strategy: str
    paraphrase_mode: Literal["disabled", "experimental"]
    llm_provider: str | None
    llm_model: str | None
    llm_unavailable_reason: str | None = None
    prompt_version: str
    prompt_sha256: str
    llm_usage: dict = {}
    degraded_reason: str | None = None
    timings_ms: dict[str, float] = {}


class TermOut(BaseModel):
    """Approved terminology entry found in the quote or claim. Not a source of the quote."""
    id: str
    term_ar: str
    language: str
    translation: str
    usage_note: str | None
    reference: str
    source_id: str


class ComparisonToken(BaseModel):
    text: str           # the token exactly as written (user side) or as stored (canonical side); never normalized
    status: Literal["MATCHED", "NORMALIZATION_ONLY", "SUBSTITUTED", "DELETED_FROM_USER_QUOTE", "ADDED_BY_USER",
                    "OUTSIDE_QUOTE", "IGNORED"]
    reasons: list[str] = []
    passage_id: str | None = None


class ComparisonDifference(BaseModel):
    kind: Literal["SUBSTITUTED", "DELETED_FROM_USER_QUOTE", "ADDED_BY_USER"]
    user: str | None = None
    canonical: str | None = None


class ComparisonSummaryItem(BaseModel):
    code: Literal["VERBATIM", "NORMALIZATION_ONLY", "PARTIAL_QUOTE", "MISSING_WORDS", "ADDED_WORDS",
                  "SUBSTITUTED_WORDS"]
    count: int | None = None
    reasons: list[str] = []


class QuoteComparison(BaseModel):
    """Deterministic token comparison of the quote with canonical text (app/services/text_diff.py). No LLM.
    definitive=True only against a resolved source; candidate comparisons are never definitive."""
    version: str
    definitive: bool
    source_type: str
    passage_ids: list[str]
    basis: Literal["imlaei", "canonical"]
    summary: list[ComparisonSummaryItem]
    user_tokens: list[ComparisonToken]
    canonical_tokens: list[ComparisonToken]
    differences: list[ComparisonDifference] = []
    quoted_range: list[int] | None = None


class MapSegment(BaseModel):
    text: str           # stored canonical text, in order (never normalized)
    kind: Literal["quoted", "near_context", "context"]


class MapNode(BaseModel):
    id: str
    kind: Literal["preceding_context", "matched", "following_context"]
    passage_id: str
    reference: str
    segments: list[MapSegment]
    evidence_ids: list[str] = []


class MapEvidence(BaseModel):
    id: str
    role: str
    passage_id: str | None
    reference: str | None
    node_id: str        # a node id, or "source" for the source metadata item


class MapRelevance(BaseModel):
    value: Literal["UNDETERMINED", "LIMITED", "RELEVANT", "NEEDS_REVIEW"]
    basis: Literal["NO_ANALYSIS", "NOT_ENABLED_FOR_SOURCE", "AI_CITED_MATCHED_ONLY", "AI_CITED_CONTEXT",
                   "SPECIALIST_OR_RESTRICTED"]
    cited_evidence_ids: list[str] = []


class MapResult(BaseModel):
    claim_status: str
    relation: str | None
    summary_source: str | None
    context_relevance: MapRelevance


class EvidenceMap(BaseModel):
    """Projection of this response's own source, context, evidence and claim analysis (app/services/evidence_map.py).
    Resolved sources only; no new text, no inference."""
    version: str
    source: dict
    nodes: list[MapNode]
    evidence: list[MapEvidence]
    claim: dict
    facts: dict
    result: MapResult


class AnalyzeResponse(BaseModel):
    request_id: str
    status: Literal["RESOLVED", "AMBIGUOUS_SOURCE", "SOURCE_NOT_FOUND"]
    quote_analysis: QuoteAnalysis
    source: SourceInfo | None
    context: Context
    evidence: EvidenceOut
    claim: ClaimOut
    claim_analysis: ClaimAnalysis
    warnings: list[Warning_] = []
    limitations: list[str]
    metadata: Metadata
    terminology: list[TermOut] = []
    sources_searched: list[str] = []   # source types searched for this quote, in priority order
    # additive (innovation v1): deterministic comparison with the resolved text; candidate comparisons for
    # near matches only (never definitive); evidence map projected from the fields above
    quote_comparison: QuoteComparison | None = None
    candidate_comparisons: list[QuoteComparison] = []
    evidence_map: EvidenceMap | None = None


class ErrorBody(BaseModel):
    code: Literal["INVALID_INPUT", "CORPUS_NOT_AVAILABLE", "SOURCE_NOT_FOUND", "AMBIGUOUS_SOURCE",
                  "SEMANTIC_SEARCH_UNAVAILABLE", "INTERNAL_ERROR", "RATE_LIMITED", "PAYLOAD_TOO_LARGE",
                  "TIMEOUT", "NOT_FOUND", "METHOD_NOT_ALLOWED"]
    message_ar: str
    message_en: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorBody
