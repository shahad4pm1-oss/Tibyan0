"""Verification contracts (Phase 1: types only, no logic).

These models encode SCIENTIFIC_POLICY.md at the schema level:
- SP-01: every religious segment carries source_id, edition and locator.
- SP-03: segments are typed source_text / commentary / ai_explanation.
- SP-09: hadith segments require a grading.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ContentLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class QuoteStatus(str, Enum):  # aligned with Phase 2 matcher (app.services.types.MatchStatus)
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    PARAPHRASED = "PARAPHRASED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class ClaimVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    OVERSTATED = "OVERSTATED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # abstention
    REQUIRES_SPECIALIST = "REQUIRES_SPECIALIST"  # referral


class SegmentType(str, Enum):
    SOURCE_TEXT = "source_text"
    COMMENTARY = "commentary"
    AI_EXPLANATION = "ai_explanation"


class SourceKind(str, Enum):
    QURAN = "quran"
    HADITH = "hadith"
    COMMENTARY = "commentary"


class VerifyRequest(BaseModel):
    quote: str = Field(min_length=2, max_length=2000)
    claim: str = Field(min_length=2, max_length=2000)


class Span(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class EvidenceItem(BaseModel):
    evidence_id: str
    kind: SourceKind
    source_id: str
    edition: str
    locator: str  # e.g. "quran:2:190", "bukhari:1234"
    text: str  # always read from the corpus, never generated
    grading: str | None = None
    grading_source: str | None = None
    author: str | None = None  # commentary author
    highlight_spans: list[Span] = []

    @model_validator(mode="after")
    def _hadith_needs_grading(self) -> "EvidenceItem":
        if self.kind == SourceKind.HADITH and not (self.grading and self.grading_source):
            raise ValueError("SP-09: hadith evidence requires grading and grading_source")
        if self.kind == SourceKind.COMMENTARY and not self.author:
            raise ValueError("SP-14: commentary requires an author")
        return self


class Segment(BaseModel):
    type: SegmentType
    text: str
    evidence_ids: list[str] = []

    @model_validator(mode="after")
    def _traceable(self) -> "Segment":
        if self.type != SegmentType.AI_EXPLANATION and not self.evidence_ids:
            raise ValueError("SP-01: religious text segments must reference evidence")
        return self


class VersionInfo(BaseModel):
    corpus_version: str
    pipeline_version: str
    llm_model: str | None = None
    embedding_model: str | None = None


class VerifyResponse(BaseModel):
    request_id: str
    content_level: ContentLevel
    quote_status: QuoteStatus
    claim_verdict: ClaimVerdict | None  # None when the pipeline stopped before analysis
    certainty: str = Field(pattern="^(direct|qualified)$")
    evidence: list[EvidenceItem]
    segments: list[Segment]
    referral: str | None = None
    disclosures: list[str]
    versions: VersionInfo
