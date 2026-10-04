"""Schema-level policy guards. Uses placeholder strings only: no religious text."""

import pytest
from pydantic import ValidationError

from app.schemas.verification import EvidenceItem, Segment, SegmentType, SourceKind


def test_hadith_without_grading_rejected():  # SP-09
    with pytest.raises(ValidationError):
        EvidenceItem(evidence_id="e1", kind=SourceKind.HADITH, source_id="s",
                     edition="ed", locator="bukhari:0", text="PLACEHOLDER")


def test_commentary_without_author_rejected():  # SP-14
    with pytest.raises(ValidationError):
        EvidenceItem(evidence_id="e1", kind=SourceKind.COMMENTARY, source_id="s",
                     edition="ed", locator="x", text="PLACEHOLDER")


def test_source_segment_requires_evidence():  # SP-01
    with pytest.raises(ValidationError):
        Segment(type=SegmentType.SOURCE_TEXT, text="PLACEHOLDER")


def test_ai_segment_allowed_without_evidence():
    assert Segment(type=SegmentType.AI_EXPLANATION, text="PLACEHOLDER")
