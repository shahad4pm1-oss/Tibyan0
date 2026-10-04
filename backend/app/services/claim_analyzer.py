"""Claim analyzer: one controlled LLM call (plus at most ONE corrective retry) over verified evidence.

The model receives only: the claim, the quote, verified source metadata, evidence objects (E-ids with
canonical text from the corpus), and level/safety instructions. User text is JSON-encoded with <, > and
= escaped, so it cannot close the untrusted-data block or forge an evidence tag.

Claim-centric output (prompt claim_analysis_v2, the default): the model decomposes the claim into
micro-assertions and is forced (provider JSON schema) to return only
{"verdict": "correct|manipulated|unrelated", "assertions": [{"claim_part", "evidence_context", "label"}]}.
That object is validated strictly (LLMMinimalOutput) and mapped deterministically onto the internal
LLMClaimOutput, so every verifier below runs unchanged. The legacy v1 shape is accepted only with the v1
prompt set, or from a test double (refused in production).

Validation chain per attempt: JSON parse -> strict schema -> citation verifier -> grounding verifier ->
safety lint. Any failure triggers the single retry with a stricter correction; a second failure yields
status REJECTED (the pipeline then reports INSUFFICIENT_EVIDENCE). Provider errors (timeout, HTTP error,
empty response) yield PROVIDER_ERROR and no verdict.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.llm.base import LLMError, LLMProvider
from app.schemas.claim_analysis import (
    LLMClaimOutput,
    LLMMinimalOutput,
    minimal_json_schema,
    provider_json_schema,
    to_claim_output,
)
from app.services import citation_verifier, safety
from app.services.content_level_router import LEVEL_GUIDANCE, Level
from app.services.evidence_builder import Evidence, with_tafsir_directive
from app.services.grounding_verifier import GroundingVerifier

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
log = logging.getLogger("tibyan.claim_analyzer")
LEGACY_PROMPT_VERSIONS = {"claim_analysis_v1"}  # relation/summary/reason schema; every later version is minimal


@dataclass
class PromptSet:
    version: str
    system: str
    user: str
    retry: str

    @property
    def minimal(self) -> bool:
        return self.version not in LEGACY_PROMPT_VERSIONS

    @property
    def sha256(self) -> str:
        return hashlib.sha256((self.system + "\x00" + self.user + "\x00" + self.retry).encode()).hexdigest()

    @classmethod
    def load(cls, version: str) -> PromptSet:
        read = lambda part: (PROMPT_DIR / f"{version}.{part}.txt").read_text(encoding="utf-8")
        # the tafsir separation directive is part of every system prompt (idempotent, see evidence_builder)
        return cls(version, with_tafsir_directive(read("system")), read("user"), read("retry"))


def escape_user_data(text: str) -> str:
    """JSON-encode and neutralise characters that could close or forge prompt blocks."""
    return (json.dumps(text, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("=", "\\u003d"))


def render_evidence(evidence: list[Evidence]) -> str:
    lines = []
    for e in evidence:
        if e.role == "metadata":
            lines.append(f'<evidence id="{e.id}" role="metadata">{e.text}</evidence>')
        else:
            lines.append(f'<evidence id="{e.id}" role="{e.role}" reference="{e.reference}">{e.text}</evidence>')
    return "\n".join(lines)


def render_user_message(p: PromptSet, quote: str, claim: str, level: Level, source: dict, match_status: str,
                        reference: str, evidence: list[Evidence]) -> str:
    return p.user.format(
        content_level=level.value, level_guidance=LEVEL_GUIDANCE[level.value],
        quote_json=escape_user_data(quote), claim_json=escape_user_data(claim),
        source_title=source["title"], source_edition=source["edition"],
        match_status=match_status, reference=reference, evidence_block=render_evidence(evidence))


def parse_output(text: str) -> dict:
    """Strict JSON object. Tolerances (formatting wrappers only, common with models without JSON mode such as
    Gemma): one surrounding ```json fence, or short text around a single top-level object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        obj = json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            raise
        obj = json.loads(t[start:end + 1])
    if not isinstance(obj, dict):
        raise TypeError("not a JSON object")
    return obj


@dataclass
class Attempt:
    issues: list[str]
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0


@dataclass
class AnalyzerOutcome:
    status: str  # OK | REJECTED | PROVIDER_ERROR | NOT_CONFIGURED
    output: LLMClaimOutput | None = None
    attempts: list[Attempt] = field(default_factory=list)
    error_category: str | None = None
    # provider's own error summary, e.g. "HTTP 404 NOT_FOUND" (adapters put only status/error codes in it,
    # never the key or user text); shown so an operator can see WHY the model call failed
    error_detail: str | None = None
    last_issues: list[str] = field(default_factory=list)

    @property
    def input_tokens(self) -> int | None:
        v = [a.input_tokens for a in self.attempts if a.input_tokens is not None]
        return sum(v) if v else None

    @property
    def output_tokens(self) -> int | None:
        v = [a.output_tokens for a in self.attempts if a.output_tokens is not None]
        return sum(v) if v else None

    @property
    def latency_ms(self) -> float:
        return sum(a.latency_ms for a in self.attempts)


class ClaimAnalyzer:
    MAX_RETRIES = 1

    def __init__(self, provider: LLMProvider | None, prompts: PromptSet, grounding: GroundingVerifier,
                 max_tokens: int = 1024, not_configured_reason: str | None = None):
        self.provider = provider
        self.prompts = prompts
        self.grounding = grounding
        self.max_tokens = max_tokens
        self.not_configured_reason = not_configured_reason

    def _check(self, text: str, evidence: list[Evidence], quote: str, claim: str, stop_reason: str | None = None
               ) -> tuple[LLMClaimOutput | None, list[str]]:
        try:
            obj = parse_output(text)
        except (ValueError, TypeError):
            # a cut-off answer is reported as such, so the operator can raise LLM_MAX_TOKENS
            truncated = str(stop_reason or "").lower() in ("max_tokens", "length")
            return None, ["OUTPUT_TRUNCATED" if truncated else "INVALID_JSON"]
        try:
            if "verdict" in obj or "assertions" in obj:
                out = to_claim_output(LLMMinimalOutput.model_validate(obj))
            elif self.prompts.minimal and not getattr(self.provider, "is_test_double", False):
                return None, ["SCHEMA_INVALID"]
            else:
                out = LLMClaimOutput.model_validate(obj)
        except ValidationError as e:
            # name the first offending field (e.g. SCHEMA_INVALID:assertions.0.evidence_context) for diagnosis
            loc = ".".join(str(x) for x in (e.errors()[0].get("loc") or ())) if e.errors() else ""
            return None, [f"SCHEMA_INVALID:{loc}" if loc else "SCHEMA_INVALID"]
        except ValueError:
            return None, ["SCHEMA_INVALID"]
        try:
            issues = citation_verifier.verify(out, evidence)
            issues += self.grounding.verify(out, evidence, quote, claim)
            issues += safety.lint_output(out)
        except Exception:
            log.exception("verifier failure")
            return None, ["VERIFIER_ERROR"]
        return (out if not issues else None), sorted(set(issues))

    def analyze(self, quote: str, claim: str, level: Level, source: dict, match_status: str, reference: str,
                evidence: list[Evidence]) -> AnalyzerOutcome:
        if self.provider is None:
            return AnalyzerOutcome("NOT_CONFIGURED", error_category="NOT_CONFIGURED")
        user = render_user_message(self.prompts, quote, claim, level, source, match_status, reference, evidence)
        schema = minimal_json_schema() if self.prompts.minimal else provider_json_schema()
        outcome = AnalyzerOutcome("REJECTED")
        message = user
        for attempt_no in range(self.MAX_RETRIES + 1):
            try:
                res = self.provider.complete_json(self.prompts.system, message, schema, self.max_tokens)
            except LLMError as e:
                outcome.status, outcome.error_category = "PROVIDER_ERROR", e.category
                outcome.error_detail = str(e)[:200] or None
                log.warning("LLM provider error: %s %s", e.category, outcome.error_detail)
                outcome.attempts.append(Attempt([e.category]))
                return outcome
            except Exception as e:
                log.exception("unexpected provider failure")
                outcome.status, outcome.error_category = "PROVIDER_ERROR", f"UNEXPECTED_{type(e).__name__}"
                outcome.attempts.append(Attempt([outcome.error_category]))
                return outcome
            out, issues = self._check(res.text, evidence, quote, claim, getattr(res, "stop_reason", None))
            outcome.attempts.append(Attempt(issues, res.usage.input_tokens, res.usage.output_tokens, res.latency_ms))
            if out is not None:
                outcome.status, outcome.output, outcome.last_issues = "OK", out, []
                return outcome
            outcome.last_issues = issues
            if attempt_no < self.MAX_RETRIES:
                message = user + self.prompts.retry.format(
                    issue_codes=", ".join(issues), allowed_ids=", ".join(e.id for e in evidence))
        outcome.status, outcome.error_category = "REJECTED", "OUTPUT_REJECTED"
        return outcome
