"""Analysis pipeline: a claim-centric analyzer in two stages.

Stage 1, ATTRIBUTION (deterministic, no LLM): retrieve -> match quote -> resolve source (Quran first, then
  Sahih al-Bukhari / Sahih Muslim) -> expand context -> build evidence (canonical text, context window,
  tafsir layer, source metadata). Output: `Attribution`.
Stage 2, MULTI-SOURCE ANALYSIS: content level + policy (ANALYZE / SCOPED / BLOCKED) -> evidence gate ->
  [LLM claim analyzer: micro-assertions over all evidence layers -> minimal schema -> citation verifier ->
  grounding verifier -> safety lint] -> safety finalize, plus terminology lookup and the deterministic quote
  comparison. Output: `ClaimStage`.
The response builder projects both stages; the API contract only gained additive fields.

The LLM is never called unless the evidence gate returns PASS. It never acts as a source: every
religious text in the response is read from the approved corpus. Never falls back to model knowledge.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.corpus.tafsir import LocalTafsirCorpus
from app.corpus.tafsir_loader import ChainedTafsir, TabariTafsirSource
from app.corpus.validation import original_text_digest
from app.db.connection import connect
from app.llm.base import LLMProvider, label
from app.llm.cost import estimate_usd
from app.llm.factory import build_provider
from app.repositories.corpus import CorpusRepository
from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    ClaimAnalysis,
    ClaimOut,
    Context,
    EvidenceItemOut,
    EvidenceOut,
    Metadata,
    QuoteAnalysis,
    SourceInfo,
    TextUnit,
    Warning_,
)
from app.services import evidence_gate, evidence_map, normalizer, safety, text_diff
from app.services.claim_analyzer import AnalyzerOutcome, ClaimAnalyzer, PromptSet
from app.services.content_level_router import Routing, route
from app.services.context_expander import ContextExpander
from app.services.evidence_builder import Evidence, EvidenceBuilder
from app.services.grounding_verifier import GroundingVerifier
from app.services.lexical_retriever import LexicalRetriever
from app.services.quote_matcher import QuoteMatcher
from app.services.rank_fusion import STRATEGIES
from app.services.semantic_retriever import SemanticRetriever
from app.services.source_resolver import Resolution, SourceResolver
from app.services.terminology import Terminology
from app.services.types import (
    AmbiguityReason,
    Candidate,
    MatchStatus,
    Passage,
    QuoteMatch,
    ResolutionStatus,
    SearchMode,
)

log = logging.getLogger("tibyan.pipeline")
audit = logging.getLogger("tibyan.audit")
_UNSET = object()

LIMITATIONS = [
    ("The corpus contains the Quran (KFGQPC Hafs) and the numbered hadith of Sahih al-Bukhari and Sahih Muslim "
     "(data path OpenITI, Shamela-derived; Muslim 1-99 not numbered in the source file: kept without a number "
     "and cited by book and chapter). Hadith search is LIMITED_PRODUCTION. Aqeedah, "
     "fiqh, history and other official sources are not ingested. Tafsir: al-Tabari (Jami' al-Bayan) fetched "
     "live from the Quran.com API, with the local Tafsir Mujahid files as fallback when al-Tabari cannot be "
     "fetched; always shown as commentary, separate from the Quranic text."),
    ("Claim analysis by a language model is enabled only for Quran results; hadith results show the text, "
     "source and grading metadata without a claim verdict."),
    "NOT_FOUND means not found in the approved corpus searched, not that the text does not exist anywhere.",
    "The context shown is a retrieved window of neighbouring ayat, not the complete scholarly context.",
    "The claim is analysed by a language model using ONLY the evidence shown; the model is not a source.",
    "Claim-relation labels have not yet been evaluated against expert-reviewed cases.",
    "Matching thresholds are configurable starting values and are not yet calibrated.",
    "A quote that does not match a source word for word is not attributed; the closest passages are shown for review.",
    "This is an AI-assisted verification tool, not a mufti or a substitute for a specialist.",
]


HADITH_STATUS = "LIMITED_PRODUCTION"
HADITH_LIMITED_MESSAGE = ("Hadith search is in LIMITED_PRODUCTION: the OpenITI files have not been cross-checked against "
                          "Shamela or Dorar, printed-edition reuse is pending verification, and retrieval was measured "
                          "on generated cases only. Only verbatim matches are attributed.")
HADITH_NEAR_MIN_COVERAGE = 0.8
HADITH_NEAR_MIN_TOKENS = 5


class CorpusNotAvailable(RuntimeError):
    pass


_UNIT_META = ("surah_number", "ayah_number", "surah_name", "collection", "collection_ar", "hadith_number", "locator",
              "numbers_covered", "book", "chapter", "grading", "grading_ar", "grading_source", "grading_authority")


def _dedupe_passages(ps) -> list[Passage]:
    seen: set[str] = set()
    return [p for p in ps if not (p.id in seen or seen.add(p.id))]


def _strength_rank(match, res) -> tuple[int, float]:
    """Textual strength of a result, used only to choose between Quran and hadith results.
    3 resolved; 2 verbatim but in several places (or too short); 1 near match (never attributed); 0 none."""
    if res.status is ResolutionStatus.RESOLVED:
        return (3, 1.0)
    if match.status is MatchStatus.AMBIGUOUS and match.reason is not AmbiguityReason.NEAR_MATCH_UNCONFIRMED:
        return (2, 1.0)
    if match.status is MatchStatus.AMBIGUOUS:
        return (1, match.coverage or 0.0)
    return (0, 0.0)


def _span_reference(ps: list[Passage]) -> str:
    if len(ps) == 1:
        return ps[0].reference
    first, last = ps[0].reference, ps[-1].reference
    if ":" in first and first.split(":")[0] == last.split(":")[0]:
        return f"{first}-{last.split(':')[1]}"
    return f"{first}-{last}"


@dataclass
class Attribution:
    """Stage 1 output: where the quote comes from and the verified evidence around it."""
    match: QuoteMatch
    res: Resolution
    fused: list[Candidate]
    searched: list[str]
    mode: SearchMode
    degraded: str | None
    context: Context
    source_out: SourceInfo | None
    matched_text: str | None
    items: list[Evidence]
    status: str
    match_status: str


@dataclass
class ClaimStage:
    """Stage 2 output: the claim analysed against every evidence layer of the attributed source."""
    routing: Routing
    gate: evidence_gate.GateResult
    outcome: object | None  # claim_analyzer.AnalyzerOutcome when the model was called
    final: safety.Final
    input_flags: list[str]
    terms: list
    comparison: object | None = None
    candidate_comparisons: list = field(default_factory=list)


class AnalysisPipeline:
    def __init__(self, settings: Settings, root: Path, provider: LLMProvider | None | object = _UNSET):
        self.s = settings
        db = Path(settings.database_path)
        db = db if db.is_absolute() else root / db
        self.index_dir = db.parent
        try:
            conn = connect(db, readonly=True)
            self.repo = CorpusRepository(conn)
            if self.repo.count_eligible() == 0:
                raise CorpusNotAvailable("corpus has no eligible passages")
            if settings.app_env == "production" and self.repo.info.get("corpus_kind") != "production":
                raise CorpusNotAvailable("production refuses a non-production (test fixture) corpus")
        except FileNotFoundError as e:
            raise CorpusNotAvailable(f"corpus database not found: {db.name}") from e
        self.corpus_version = self.repo.info.get("corpus_version", settings.corpus_version)
        self.lexical = LexicalRetriever(self.repo, settings.lexical_top_k)
        self.semantic = SemanticRetriever(self.repo, self.index_dir, settings.embedding_provider,
                                          settings.embedding_model, settings.app_env, settings.semantic_top_k)
        if not self.semantic.available:
            log.warning("semantic retrieval unavailable, running LEXICAL_ONLY: %s", self.semantic.reason)
        paraphrase_mode = settings.paraphrase_mode
        if paraphrase_mode != "disabled" and settings.app_env == "production":
            log.warning("PARAPHRASE_MODE=%s refused in production; using 'disabled'", paraphrase_mode)
            paraphrase_mode = "disabled"
        self.paraphrase_mode = paraphrase_mode
        self.matcher = QuoteMatcher(self.repo, settings.min_partial_tokens, settings.max_span_ayat,
                                    settings.paraphrase_min_coverage, settings.paraphrase_min_margin,
                                    paraphrase_mode=paraphrase_mode)
        self.resolver = SourceResolver(self.repo)
        # hadith: own BM25 index, phrase/partial matching inside one hadith only (no spans, no near-match
        # attribution), no semantic retrieval
        self.repo_hadith = self.repo.for_index("hadith_fts")
        self.has_hadith = self.repo.count_by_type().get("hadith", 0) > 0
        self.hadith_tokenize = normalizer.hadith_tokens          # hnorm-v1: honorifics, NFKC (search only)
        self.hadith_norm_version = normalizer.HADITH_VERSION
        self.lexical_hadith = LexicalRetriever(self.repo_hadith, settings.lexical_top_k, self.hadith_tokenize)
        # near matches against long hadith texts are noisier than against ayat: list them only for
        # quotes of >= 5 words with >= 80% token coverage (uncalibrated starting values)
        self.matcher_hadith = QuoteMatcher(self.repo_hadith, settings.min_partial_tokens, 1,
                                           HADITH_NEAR_MIN_COVERAGE, settings.paraphrase_min_margin,
                                           paraphrase_mode="disabled", fuzzy_min_tokens=HADITH_NEAR_MIN_TOKENS,
                                           tokenize=self.hadith_tokenize, alt_tokenize=normalizer.nfkc_tokens)
        self.terminology = Terminology(conn)
        self._source_types: dict[str, str | None] = {}
        self.expander = ContextExpander(self.repo, settings.context_window)
        tafsir_dir = Path(settings.tafsir_data_dir)
        tafsir_dir = tafsir_dir if tafsir_dir.is_absolute() else root / tafsir_dir
        self.tafsir = self._build_tafsir(settings, tafsir_dir) if settings.tafsir_enabled else None
        self.builder = EvidenceBuilder(self.tafsir, settings.tafsir_max_chars)
        # corpus integrity: digest of all canonical text must equal the digest recorded at build time
        self.corpus_integrity_ok = original_text_digest(self.repo.conn) == self.repo.info.get("original_text_sha256")
        if not self.corpus_integrity_ok:
            log.error("corpus integrity check FAILED: claim analysis disabled")
        if provider is _UNSET:
            ps = build_provider(settings)
            self.llm, self.llm_unavailable_reason = ps.provider, ps.reason
        else:
            self.llm, self.llm_unavailable_reason = provider, (None if provider else "no provider")
        if self.llm is not None and self.llm.is_test_double and settings.app_env == "production":
            self.llm, self.llm_unavailable_reason = None, "test doubles are refused in production"
        self.prompts = PromptSet.load(settings.prompt_version)
        self.analyzer = ClaimAnalyzer(self.llm, self.prompts, GroundingVerifier(self.repo), settings.llm_max_tokens,
                                      self.llm_unavailable_reason)

    @staticmethod
    def _build_tafsir(settings: Settings, tafsir_dir: Path):
        local = LocalTafsirCorpus(tafsir_dir)
        provider = settings.tafsir_provider.lower()
        if provider == "local":
            return local
        tabari = TabariTafsirSource(base_url=settings.tafsir_api_base_url,
                                    resource_id=settings.tafsir_api_resource_id,
                                    timeout_s=settings.tafsir_api_timeout_s, max_retries=0,
                                    call_timeout_s=settings.tafsir_api_timeout_s + 1)
        return ChainedTafsir(tabari) if provider == "tabari_only" else ChainedTafsir(tabari, local)

    def hadith_candidates(self, quote: str) -> list[Candidate]:
        """Hadith candidate ranking: verbatim phrase hits (under hnorm-v1 OR NFKC+norm-v1) first, including hits
        BM25 did not rank in its top k, then BM25 order. Ranking only; attribution is decided by the matcher."""
        lex = self.lexical_hadith.search(quote)
        hits = _dedupe_passages(p for tk in (self.hadith_tokenize, normalizer.nfkc_tokens)
                                for p in self.repo_hadith.phrase_hits(tk(quote)))
        seen = {c.passage.id for c in lex}
        extra = [p for p in hits if p.id not in seen]
        lex = lex + [Candidate(passage=p, lexical_rank=len(lex) + i + 1) for i, p in enumerate(extra)]
        return STRATEGIES["lexical_first"](lex, [], k=self.s.rrf_k, top_n=max(self.s.hybrid_top_n, 10),
                                           exact_ids={p.id for p in hits})

    def _unit(self, p: Passage) -> TextUnit:
        meta = {k: p.metadata[k] for k in _UNIT_META if k in p.metadata}
        src = self._source_types.get(p.source_id)
        if src is None:
            row = self.repo.source(p.source_id)
            src = self._source_types[p.source_id] = row["source_type"] if row else None
        return TextUnit(passage_id=p.id, reference=p.reference, text=p.original_text, metadata=meta, source_type=src)

    def _evidence_intact(self, evidence: list[Evidence]) -> bool:
        if not self.corpus_integrity_ok:
            return False
        for e in evidence:
            if e.passage_id:
                p = self.repo.get(e.passage_id)
                if p is None or p.original_text != e.text:
                    return False
        return True

    # ------------------------------------------------------------------ Stage 1: attribution
    def attribute(self, quote: str, warnings: list[Warning_], t: dict[str, float]) -> Attribution:
        """Deterministic attribution of the quote to an approved source. Never calls the LLM."""
        t0 = time.perf_counter()
        # ---- 1a. Quran (priority source; byte-identical Phase 2 retrieval path)
        lex = self.lexical.search(quote)
        t["lexical"] = (time.perf_counter() - t0) * 1000
        sem, mode, degraded = [], SearchMode.HYBRID, None
        t1 = time.perf_counter()
        if self.semantic.available:
            try:
                sem = self.semantic.search(quote)
            except Exception as e:  # noqa: BLE001
                mode, degraded = SearchMode.LEXICAL_ONLY, f"{type(e).__name__}"
                log.warning("semantic search failed: %s", e)
        else:
            mode, degraded = SearchMode.LEXICAL_ONLY, self.semantic.reason
        if mode is SearchMode.LEXICAL_ONLY:
            warnings.append(Warning_(code="SEMANTIC_SEARCH_UNAVAILABLE",
                                     message="Semantic search unavailable; results use lexical search only."))
        t["semantic"] = (time.perf_counter() - t1) * 1000

        t2 = time.perf_counter()
        exact = {p.id for p in self.repo.phrase_hits(normalizer.tokens(quote))}
        fuse = STRATEGIES[self.s.hybrid_strategy]
        fused = fuse(lex, sem, k=self.s.rrf_k, top_n=max(self.s.hybrid_top_n, 10), exact_ids=exact)
        match = self.matcher.match(quote, fused)
        res = self.resolver.resolve(match)
        searched = ["quran"]
        t["match_resolve"] = (time.perf_counter() - t2) * 1000

        # ---- 1b. Hadith (Sahih al-Bukhari, Sahih Muslim), only if the Quran did not resolve the quote.
        #      Separate BM25 index; no semantic retrieval; no spans across hadith. The stronger textual
        #      result wins; on equal strength the Quran result is kept. Never a near match as a hadith.
        if self.has_hadith and _strength_rank(match, res)[0] < 2:
            t3h = time.perf_counter()
            fused_h = self.hadith_candidates(quote)
            match_h = self.matcher_hadith.match(quote, fused_h)
            res_h = self.resolver.resolve(match_h)
            searched.append("hadith")
            q_rank = _strength_rank(match, res)
            # a quote found verbatim in the Quran (even in several ayat) is never re-attributed to a hadith
            if q_rank[0] < 2 and _strength_rank(match_h, res_h) > q_rank:
                match, res, fused = match_h, res_h, fused_h
            t["hadith_search"] = (time.perf_counter() - t3h) * 1000

        # ---- 1c. Context window and evidence objects (canonical text, context, tafsir layer, metadata)
        context, source_out, matched_text, items = Context(), None, None, []
        if res.status is ResolutionStatus.RESOLVED:
            ctx = self.expander.expand(res.passages, res.source)
            items = self.builder.build(ctx, res.source)
            context = Context(kind=ctx.kind, before=[self._unit(p) for p in ctx.before],
                              matched=[self._unit(p) for p in ctx.matched],
                              after=[self._unit(p) for p in ctx.after],
                              supporting_material=ctx.supporting_material)
            source_out = SourceInfo(source_id=res.source["id"], title=res.source["title"],
                                    reference=_span_reference(res.passages), source_url=res.source["source_url"],
                                    edition=res.source["edition"], publisher=res.source["publisher"],
                                    source_type=res.source["source_type"], author=res.source.get("author"),
                                    verification_status=res.source["verification_status"])
            matched_text = " ".join(p.original_text for p in res.passages)

        status = {ResolutionStatus.RESOLVED: "RESOLVED", ResolutionStatus.AMBIGUOUS: "AMBIGUOUS_SOURCE",
                  ResolutionStatus.NOT_FOUND: "SOURCE_NOT_FOUND"}[res.status]
        match_status = match.status.value
        if res.status is ResolutionStatus.NOT_FOUND and match.status is not MatchStatus.NOT_FOUND:
            match_status = MatchStatus.NOT_FOUND.value  # failed re-verification
        if res.source and res.source.get("source_type") == "hadith":
            warnings.append(Warning_(code="HADITH_LIMITED_PRODUCTION", message=HADITH_LIMITED_MESSAGE))
        return Attribution(match, res, fused, searched, mode, degraded, context, source_out, matched_text, items,
                           status, match_status)

    # ------------------------------------------------------------------ Stage 2: multi-source analysis
    def analyze_claim(self, quote: str, claim: str, a: Attribution, t: dict[str, float]) -> ClaimStage:
        """Claim-centric analysis over every evidence layer Stage 1 attributed (text, context, tafsir,
        terminology). Level C claims are SCOPED (text-context analysis, no standalone ruling); level D
        never reaches the model."""
        t3 = time.perf_counter()
        terms: list = []  # glossary sample hints are not part of the product (removed 2026-10-04)
        routing = route(claim)
        input_flags = safety.screen_input(quote, claim)  # logged only; never changes behaviour
        gate = evidence_gate.evaluate(
            routing.level, a.res, a.match, a.items, len(a.context.matched), self._evidence_intact(a.items),
            len(normalizer.tokens(quote)), self.s.gate_min_quote_tokens, self.s.strength_min_tokens_sufficient)
        outcome = None
        if gate.decision is evidence_gate.GateDecision.PASS:
            try:
                outcome = self.analyzer.analyze(quote, claim, routing.level, a.res.source, a.match_status,
                                                a.source_out.reference, a.items)
            except Exception as e:
                log.exception("claim analyzer failed")
                outcome = AnalyzerOutcome("PROVIDER_ERROR", error_category=f"ANALYZER_CRASH_{type(e).__name__}")
        final = safety.finalize(routing.level, gate, outcome)
        t["claim_analysis"] = (time.perf_counter() - t3) * 1000

        # ---- deterministic quote comparison (display only; never changes the decisions above)
        t4 = time.perf_counter()
        stage = ClaimStage(routing, gate, outcome, final, input_flags, terms)
        res, match = a.res, a.match
        if res.status is ResolutionStatus.RESOLVED and res.source:
            stage.comparison = text_diff.compare(quote, res.passages, res.source.get("source_type") or "", True)
        elif match.status is MatchStatus.AMBIGUOUS and match.reason is AmbiguityReason.NEAR_MATCH_UNCONFIRMED:
            for p in res.alternatives[:3]:
                row = self.repo.source(p.source_id)
                c = text_diff.compare(quote, [p], (row or {}).get("source_type") or "", False)
                if c:
                    stage.candidate_comparisons.append(c)
        t["comparison"] = (time.perf_counter() - t4) * 1000
        return stage

    def analyze(self, req: AnalyzeRequest, request_id: str | None = None) -> AnalyzeResponse:
        rid = request_id or str(uuid.uuid4())
        t: dict[str, float] = {}
        t0 = time.perf_counter()
        warnings: list[Warning_] = []

        a = self.attribute(req.quote, warnings, t)              # Stage 1
        c = self.analyze_claim(req.quote, req.claim, a, t)      # Stage 2
        match, res, fused, context = a.match, a.res, a.fused, a.context
        routing, gate, outcome, final = c.routing, c.gate, c.outcome, c.final
        status, match_status, mode, items = a.status, a.match_status, a.mode, a.items

        claim_analysis = ClaimAnalysis(
            status=final.status, relation=final.relation, summary=final.summary,
            summary_source=final.summary_source, reason=final.reason, evidence_ids=final.evidence_ids,
            key_evidence=final.key_evidence, needs_specialist=final.needs_specialist,
            uncertainty_reason=final.uncertainty_reason, referral=final.referral,
            content_level=routing.level.value, level_policy=routing.policy.value, level_scope=routing.scope,
            verdict=final.verdict, assertions=final.assertions, level_rules=routing.matched,
            gate={"decision": gate.decision.value, "reasons": gate.reasons},
            safety_overrides=final.safety_overrides, attempts=len(outcome.attempts) if outcome else 0,
            disclosure=safety.DISCLOSURE)
        # ---- evidence & context map: projection of the outputs above (resolved sources only)
        t5 = time.perf_counter()
        emap = evidence_map.project(res.source if res.status is ResolutionStatus.RESOLVED else None, context, items,
                                    c.comparison, req.claim, claim_analysis.model_dump())
        t["evidence_map"] = (time.perf_counter() - t5) * 1000

        prov, model = label(self.llm)
        usage = {}
        if outcome is not None and outcome.attempts:
            usage = {"attempts": len(outcome.attempts), "input_tokens": outcome.input_tokens,
                     "output_tokens": outcome.output_tokens, "latency_ms": round(outcome.latency_ms, 1),
                     "cost_usd": estimate_usd(outcome.input_tokens, outcome.output_tokens,
                                              self.s.llm_price_input_per_mtok, self.s.llm_price_output_per_mtok)}
        t["total"] = (time.perf_counter() - t0) * 1000

        # ---- audit log: ids, codes and timings only; never raw user text (SP-07)
        audit.info(json.dumps({
            "request_id": rid, "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": status, "match_status": match_status,
            "retrieved_ids": [c.passage.id for c in fused[:10]], "evidence_ids": [e.id for e in items],
            "evidence_passages": [e.passage_id for e in items if e.passage_id],
            "content_level": routing.level.value, "level_policy": routing.policy.value, "level_rules": [r.split(":")[0] for r in routing.matched],
            "gate": gate.decision.value, "gate_reasons": gate.reasons, "strength": gate.strength.value,
            "claim_status": final.status, "relation": final.relation, "overrides": final.safety_overrides,
            "verdict": final.verdict, "input_flags": c.input_flags, "llm_provider": prov, "llm_model": model,
            "prompt_version": self.prompts.version, "attempts": usage.get("attempts", 0),
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "error_category": outcome.error_category if outcome else None,
            "attempt_issues": [a.issues for a in outcome.attempts] if outcome else [],
            "stages_ms": {"attribution": round(sum(t.get(k, 0) for k in ("lexical", "semantic", "match_resolve",
                                                                         "hadith_search")), 1),
                          "analysis": round(t.get("claim_analysis", 0) + t.get("comparison", 0), 1)},
            "search_mode": mode.value, "latency_ms": round(t["total"], 1)}, ensure_ascii=False))

        return AnalyzeResponse(
            request_id=rid,
            status=status,
            quote_analysis=QuoteAnalysis(
                match_status=match_status, matched_text=a.matched_text, match_method=match.method,
                token_coverage=round(match.coverage, 3) if match.coverage is not None else None,
                alternatives=[self._unit(p) for p in res.alternatives], alternatives_total=res.alternatives_total,
                ambiguity_reason=match.reason.value if match.reason else None),
            source=a.source_out,
            context=context,
            evidence=EvidenceOut(strength=gate.strength.value, items=[EvidenceItemOut(**e.to_dict()) for e in items]),
            claim=ClaimOut(text=req.claim),
            claim_analysis=claim_analysis,
            warnings=warnings,
            limitations=LIMITATIONS,
            terminology=c.terms,
            sources_searched=a.searched,
            quote_comparison=c.comparison,
            candidate_comparisons=c.candidate_comparisons,
            evidence_map=emap,
            metadata=Metadata(corpus_version=self.corpus_version, retrieval_version=self.s.retrieval_version,
                              pipeline_version=self.s.pipeline_version, normalizer_version=normalizer.VERSION,
                              embedding_model=self.semantic.model_label, search_mode=mode.value,
                              ranking_strategy=self.s.hybrid_strategy if mode is SearchMode.HYBRID else "bm25",
                              paraphrase_mode=self.paraphrase_mode, llm_provider=prov, llm_model=model,
                              llm_unavailable_reason=self.llm_unavailable_reason,
                              prompt_version=self.prompts.version, prompt_sha256=self.prompts.sha256[:16],
                              llm_usage=usage, degraded_reason=a.degraded,
                              timings_ms={k: round(v, 1) for k, v in t.items()}),
        )
