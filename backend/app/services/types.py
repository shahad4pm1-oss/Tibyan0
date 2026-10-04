from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MatchStatus(str, Enum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    PARAPHRASED = "PARAPHRASED"  # RESERVED/EXPERIMENTAL: never emitted when PARAPHRASE_MODE=disabled
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class AmbiguityReason(str, Enum):
    MULTIPLE_LOCATIONS = "MULTIPLE_LOCATIONS"  # the exact wording occurs in several passages
    NEAR_MATCH_UNCONFIRMED = "NEAR_MATCH_UNCONFIRMED"  # no exact/partial match; closest passages listed only
    QUOTE_TOO_SHORT = "QUOTE_TOO_SHORT"


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class SearchMode(str, Enum):
    HYBRID = "HYBRID"
    LEXICAL_ONLY = "LEXICAL_ONLY"


@dataclass
class Passage:
    id: str
    rowid: int
    source_id: str
    reference: str
    sequence: int
    parent_id: str | None
    original_text: str
    normalized_text: str
    normalized_text_alt: str | None
    metadata: dict


@dataclass
class Candidate:
    passage: Passage
    lexical_rank: int | None = None
    lexical_score: float | None = None  # bm25 (lower is better in SQLite)
    semantic_rank: int | None = None
    semantic_score: float | None = None  # cosine similarity
    rrf_score: float = 0.0
    exact_phrase: bool = False


@dataclass
class QuoteMatch:
    status: MatchStatus
    method: str  # phrase | span | fuzzy | none
    passages: list[Passage] = field(default_factory=list)  # matched passage(s), in order
    coverage: float | None = None
    alternatives: list[Passage] = field(default_factory=list)  # for AMBIGUOUS
    alternatives_total: int = 0
    reason: AmbiguityReason | None = None
