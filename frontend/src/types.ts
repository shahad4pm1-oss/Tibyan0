export type Relation = "SUPPORTED" | "OVERSTATED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE" | "REQUIRES_SPECIALIST";

export type MatchStatus = "EXACT" | "PARTIAL" | "PARAPHRASED" | "AMBIGUOUS" | "NOT_FOUND";

export type SourceType = "quran" | "hadith" | "tafsir" | "aqeedah" | "fiqh" | "seerah" | "history" | "dawah"
  | "shubuhat" | "dictionary" | "synthetic_fixture" | string;

export type UnitMeta = {
  surah_number?: number; ayah_number?: number; surah_name?: string;
  collection?: string; collection_ar?: string; hadith_number?: string; numbers_covered?: number[];
  book?: string | null; chapter?: string | null; grading?: string; grading_ar?: string;
  grading_source?: string; grading_authority?: string;
  [k: string]: unknown;
};

export type TextUnit = {
  passage_id: string;
  reference: string;
  text: string;
  metadata: UnitMeta;
  source_type?: SourceType | null;
};

export type EvidenceItem = {
  id: string;
  passage_id: string | null;
  source_id: string;
  reference: string | null;
  text: string;
  role: "matched_source" | "preceding_context" | "following_context" | "source_commentary" | "metadata";
  source_title?: string | null;
  edition?: string | null;
  metadata?: UnitMeta | null;
  source_type?: SourceType | null;
  verification_status?: string | null;
};

export type TokenStatus = "MATCHED" | "NORMALIZATION_ONLY" | "SUBSTITUTED" | "DELETED_FROM_USER_QUOTE" | "ADDED_BY_USER"
  | "OUTSIDE_QUOTE" | "IGNORED";

export type ComparisonToken = { text: string; status: TokenStatus; reasons: string[]; passage_id?: string | null };

export type QuoteComparison = {
  version: string;
  definitive: boolean;
  source_type: string;
  passage_ids: string[];
  basis: "imlaei" | "canonical";
  summary: { code: "VERBATIM" | "NORMALIZATION_ONLY" | "PARTIAL_QUOTE" | "MISSING_WORDS" | "ADDED_WORDS" | "SUBSTITUTED_WORDS";
    count?: number | null; reasons: string[] }[];
  user_tokens: ComparisonToken[];
  canonical_tokens: ComparisonToken[];
  differences: { kind: "SUBSTITUTED" | "DELETED_FROM_USER_QUOTE" | "ADDED_BY_USER"; user: string | null; canonical: string | null }[];
  quoted_range: [number, number] | null;
};

export type EvidenceMap = {
  version: string;
  source: { source_id: string; title: string; source_type: string; reference: string };
  nodes: { id: string; kind: "preceding_context" | "matched" | "following_context"; passage_id: string; reference: string;
    segments: { text: string; kind: "quoted" | "near_context" | "context" }[]; evidence_ids: string[] }[];
  evidence: { id: string; role: string; passage_id: string | null; reference: string | null; node_id: string }[];
  claim: { text: string };
  facts: { quoted_words: number; omitted_words_in_matched: number; preceding_units: number; following_units: number;
    context_kind: "hadith_only" | "neighbouring_ayat" };
  result: { claim_status: string; relation: Relation | null; summary_source: string | null;
    context_relevance: { value: "UNDETERMINED" | "LIMITED" | "RELEVANT" | "NEEDS_REVIEW";
      basis: "NO_ANALYSIS" | "NOT_ENABLED_FOR_SOURCE" | "AI_CITED_MATCHED_ONLY" | "AI_CITED_CONTEXT" | "SPECIALIST_OR_RESTRICTED";
      cited_evidence_ids: string[] } };
};

export type AnalyzeResponse = {
  request_id: string;
  status: "RESOLVED" | "AMBIGUOUS_SOURCE" | "SOURCE_NOT_FOUND";
  quote_analysis: {
    match_status: MatchStatus;
    matched_text: string | null;
    match_method: string;
    token_coverage: number | null;
    alternatives: TextUnit[];
    alternatives_total: number;
    ambiguity_reason: "MULTIPLE_LOCATIONS" | "NEAR_MATCH_UNCONFIRMED" | "QUOTE_TOO_SHORT" | null;
  };
  source: {
    source_id: string;
    title: string;
    reference: string;
    source_url: string | null;
    edition: string;
    publisher: string | null;
    source_type: SourceType;
    author?: string | null;
    verification_status?: string;
  } | null;
  context: { kind: string; before: TextUnit[]; matched: TextUnit[]; after: TextUnit[]; supporting_material: unknown[] };
  evidence: { strength: "SUFFICIENT" | "LIMITED" | "INSUFFICIENT"; items: EvidenceItem[] };
  claim: { text: string };
  claim_analysis: {
    status: "COMPLETED" | "ABSTAINED" | "REFERRED" | "ANALYSIS_UNAVAILABLE" | "AI_OUTPUT_REJECTED";
    relation: Relation | null;
    summary: string | null;
    summary_source: "ai" | "system_template" | null;
    reason: string | null;
    evidence_ids: string[];
    key_evidence: { evidence_id: string; relevance: string }[];
    needs_specialist: boolean;
    uncertainty_reason: string | null;
    referral: string | null;
    content_level: "A" | "B" | "C" | "D";
    level_policy?: "ANALYZE" | "SCOPED" | "BLOCKED" | null;
    level_scope?: string[];
    verdict?: Verdict | null;
    assertions?: Assertion[];
    level_rules: string[];
    gate: { decision: "PASS" | "INSUFFICIENT" | "SPECIALIST_REQUIRED"; reasons: string[] };
    safety_overrides: string[];
    attempts: number;
    disclosure: string;
  };
  warnings: { code: string; message: string }[];
  sources_searched?: SourceType[];
  limitations: string[];
  quote_comparison?: QuoteComparison | null;
  candidate_comparisons?: QuoteComparison[];
  evidence_map?: EvidenceMap | null;
  metadata: {
    corpus_version: string;
    retrieval_version: string;
    pipeline_version: string;
    normalizer_version: string;
    embedding_model: string | null;
    search_mode: "HYBRID" | "LEXICAL_ONLY";
    ranking_strategy: string;
    paraphrase_mode: "disabled" | "experimental";
    llm_provider: string | null;
    llm_model: string | null;
    llm_unavailable_reason: string | null;
    prompt_version: string;
    prompt_sha256: string;
    degraded_reason: string | null;
    timings_ms: Record<string, number>;
  };
};

export type Verdict = "correct" | "manipulated" | "unrelated";
export type AssertionLabel = "supported" | "overstated" | "contradicted" | "not_in_evidence" | "requires_specialist";
export type Assertion = { claim_part: string; evidence_context: string; label: AssertionLabel };

export type ApiError = {
  request_id: string;
  error: { code: string; message_ar: string; message_en: string };
};
