"""Strict schemas for the LLM's claim-vs-evidence output.

Two shapes:
- LLMMinimalOutput (prompt claim_analysis_v2, the default): the claim-centric minimal schema the model is
  forced to return: {"verdict": "correct|manipulated|unrelated", "assertions": [{"claim_part",
  "evidence_context", "label"}]}. The claim is decomposed into micro-assertions, each judged on its own.
  `to_claim_output()` maps it deterministically onto LLMClaimOutput so the citation verifier, grounding
  verifier, safety lint and finalizer keep working unchanged.
- LLMClaimOutput: the internal normalized form (and the legacy v1 model output).

Malformed or internally inconsistent outputs are REJECTED, never repaired. The single exception is
letter case of the `relation` label, which the vendor documents as not guaranteed for enums: an
otherwise identical label in different case is accepted (documented in docs/PROMPTING.md).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Relation = Literal["SUPPORTED", "OVERSTATED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"]
RELATIONS = ("SUPPORTED", "OVERSTATED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST")
SUBSTANTIVE = {"SUPPORTED", "OVERSTATED", "CONTRADICTED"}
ABSTAINING = {"INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"}
_EID = re.compile(r"^E[1-9][0-9]{0,2}$")


class KeyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    relevance: str = Field(min_length=1, max_length=400)

    @field_validator("evidence_id")
    @classmethod
    def _eid(cls, v: str) -> str:
        if not _EID.match(v):
            raise ValueError("evidence_id must look like E1, E2, ...")
        return v


Verdict = Literal["correct", "manipulated", "unrelated"]
VERDICTS = ("correct", "manipulated", "unrelated")
AssertionLabel = Literal["supported", "overstated", "contradicted", "not_in_evidence", "requires_specialist"]
ASSERTION_LABELS = ("supported", "overstated", "contradicted", "not_in_evidence", "requires_specialist")
# an evidence id may sit directly against Arabic letters ("وE1", "الدليلE2"), so no \b word boundary here
_CITED_EID = re.compile(r"(?<![A-Za-z0-9_])E\s?([1-9][0-9]{0,2})(?![0-9])")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
MAX_ASSERTIONS = 10


def _token(v):
    """'Not in evidence' / 'NOT-IN-EVIDENCE' / 'Over-stated' -> 'not_in_evidence' / 'overstated'."""
    if not isinstance(v, str):
        return v
    key = re.sub(r"[\s\-_]+", "", v.lower())
    return _CANON.get(key, v)


_CANON = {t.replace("_", ""): t for t in (*VERDICTS, *ASSERTION_LABELS)}


class Assertion(BaseModel):
    """One micro-assertion of the user's claim and how the cited evidence bears on it."""
    model_config = ConfigDict(extra="forbid")

    # generous limits: over-long text is clipped when mapped for display, never a reason to drop the analysis
    claim_part: str = Field(min_length=1, max_length=600)
    evidence_context: str = Field(min_length=1, max_length=1500)
    label: AssertionLabel

    @field_validator("label", mode="before")
    @classmethod
    def _case(cls, v):
        return _token(v)

    @property
    def cited_ids(self) -> list[str]:
        return list(dict.fromkeys(f"E{n}" for n in _CITED_EID.findall(self.evidence_context.translate(_AR_DIGITS))))

    @model_validator(mode="after")
    def _cites(self) -> Assertion:
        if self.label in ("supported", "overstated", "contradicted") and not self.cited_ids:
            raise ValueError("a judged assertion must cite an evidence id (E1, E2, ...) in evidence_context")
        return self


class LLMMinimalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    assertions: list[Assertion] = Field(min_length=1, max_length=MAX_ASSERTIONS)

    @field_validator("verdict", mode="before")
    @classmethod
    def _case(cls, v):
        return _token(v)

    @property
    def derived_verdict(self) -> str:
        """The verdict the per-part labels support. The parts are the judgment; the overall verdict follows them:
        any overstated/contradicted part, or supported parts mixed with parts the evidence does not contain
        (the claim adds meaning) -> manipulated; only supported -> correct; nothing supported -> unrelated."""
        labels = {a.label for a in self.assertions} - {"requires_specialist"}
        if labels & {"overstated", "contradicted"} or {"supported", "not_in_evidence"} <= labels:
            return "manipulated"
        if labels == {"supported"}:
            return "correct"
        return "unrelated"


LABEL_AR = {"supported": "مؤيَّد", "overstated": "مبالغ فيه", "contradicted": "مخالف للنص",
            "not_in_evidence": "غير وارد في الدليل", "requires_specialist": "يحتاج إلى مختص"}
VERDICT_SUMMARY = {
    "correct": "أجزاء الادعاء التي أمكن فحصها تتوافق مع النص المعروض وسياقه في حدود الأدلة المقدمة.",
    "manipulated": "الادعاء يحمّل النص ما لا يدل عليه سياقه المعروض، أو يخالفه في بعض أجزائه.",
    "unrelated": "النص المعروض وسياقه لا يتناولان مضمون الادعاء.",
    "specialist": "أجزاء الادعاء تتطلب نظرًا علميًا من مختص مؤهل، فلم يُحكم عليها.",
}


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def to_claim_output(m: LLMMinimalOutput) -> LLMClaimOutput:
    """Deterministic mapping of the minimal schema onto the internal form.
    correct -> SUPPORTED; manipulated -> CONTRADICTED if any part is contradicted, else OVERSTATED;
    unrelated -> INSUFFICIENT_EVIDENCE; every part requires_specialist -> REQUIRES_SPECIALIST.
    A model verdict that disagrees with its own per-part labels is reconciled to the labels (noted
    VERDICT_RECONCILED) instead of discarding the whole analysis."""
    labels = {a.label for a in m.assertions}
    verdict, notes = m.verdict, []
    if labels != {"requires_specialist"} and m.derived_verdict != m.verdict:
        verdict, notes = m.derived_verdict, ["VERDICT_RECONCILED"]
    if labels == {"requires_specialist"}:
        relation, key = "REQUIRES_SPECIALIST", "specialist"
    elif verdict == "correct":
        relation, key = "SUPPORTED", "correct"
    elif verdict == "manipulated":
        relation, key = ("CONTRADICTED" if "contradicted" in labels else "OVERSTATED"), "manipulated"
    else:
        relation, key = "INSUFFICIENT_EVIDENCE", "unrelated"
    ids: list[str] = []
    key_evidence: list[dict] = []
    for a in m.assertions:
        for i in a.cited_ids:
            if i not in ids:
                ids.append(i)
                key_evidence.append({"evidence_id": i, "relevance": _clip(a.evidence_context, 400)})
    reason = " ؛ ".join(f"[{LABEL_AR[a.label]}] {a.evidence_context}" for a in m.assertions)
    uncertainty = None
    if relation == "INSUFFICIENT_EVIDENCE":
        uncertainty = "UNRELATED: " + VERDICT_SUMMARY["unrelated"]
    elif relation == "REQUIRES_SPECIALIST":
        uncertainty = "ASSERTIONS_REQUIRE_SPECIALIST: " + VERDICT_SUMMARY["specialist"]
    return LLMClaimOutput(
        relation=relation, summary=VERDICT_SUMMARY[key], reason=_clip(reason, 1200),
        evidence_ids=ids[:20], key_evidence=key_evidence[:10],
        needs_specialist=relation == "REQUIRES_SPECIALIST", uncertainty_reason=uncertainty,
        verdict=verdict, assertions=m.assertions, notes=notes)


class LLMClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: Relation
    summary: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(max_length=20)
    key_evidence: list[KeyEvidence] = Field(max_length=10)
    needs_specialist: bool
    uncertainty_reason: str | None = Field(default=None, max_length=600)
    # set only when the output came from the minimal claim-centric schema
    verdict: Verdict | None = None
    assertions: list[Assertion] = Field(default_factory=list, max_length=MAX_ASSERTIONS)
    notes: list[str] = Field(default_factory=list)  # deterministic adjustments, e.g. VERDICT_RECONCILED

    @field_validator("relation", mode="before")
    @classmethod
    def _case(cls, v):
        if isinstance(v, str) and v.upper() in RELATIONS:
            return v.upper()
        return v

    @field_validator("evidence_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        for e in v:
            if not _EID.match(e):
                raise ValueError(f"invalid evidence id {e!r}")
        if len(set(v)) != len(v):
            raise ValueError("duplicate evidence ids")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> LLMClaimOutput:
        if self.relation in SUBSTANTIVE:
            if not self.evidence_ids or not self.key_evidence:
                raise ValueError("a substantive relation must cite evidence_ids and key_evidence")
            if self.needs_specialist:
                raise ValueError("needs_specialist=true contradicts a substantive relation")
        if self.relation == "REQUIRES_SPECIALIST" and not self.needs_specialist:
            raise ValueError("REQUIRES_SPECIALIST requires needs_specialist=true")
        if self.relation in ABSTAINING and not (self.uncertainty_reason or "").strip():
            raise ValueError("an abstaining relation requires uncertainty_reason")
        if {k.evidence_id for k in self.key_evidence} - set(self.evidence_ids):
            raise ValueError("key_evidence must be a subset of evidence_ids")
        return self


def provider_json_schema() -> dict:
    """Schema sent to the provider. Uses only features the vendor documents as supported
    (types, enum, required, nested objects, additionalProperties=false). Length limits and
    consistency rules are enforced locally by LLMClaimOutput."""
    return {
        "type": "object",
        "properties": {
            "relation": {"type": "string", "enum": list(RELATIONS)},
            "summary": {"type": "string"},
            "reason": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "key_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"evidence_id": {"type": "string"}, "relevance": {"type": "string"}},
                    "required": ["evidence_id", "relevance"],
                    "additionalProperties": False,
                },
            },
            "needs_specialist": {"type": "boolean"},
            "uncertainty_reason": {"type": ["string", "null"]},
        },
        "required": ["relation", "summary", "reason", "evidence_ids", "key_evidence", "needs_specialist",
                     "uncertainty_reason"],
        "additionalProperties": False,
    }


def minimal_json_schema() -> dict:
    """Provider schema for the claim-centric minimal output (prompt claim_analysis_v2)."""
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "assertions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_part": {"type": "string"},
                        "evidence_context": {"type": "string"},
                        "label": {"type": "string", "enum": list(ASSERTION_LABELS)},
                    },
                    "required": ["claim_part", "evidence_context", "label"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["verdict", "assertions"],
        "additionalProperties": False,
    }
