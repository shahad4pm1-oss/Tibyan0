"""Multi-source evaluation (2026-10-02): hadith retrieval and matching, cross-source safety, terminology lookup.

Reported separately per source type; no global score. Cases are GENERATED from the corpus itself (seeded
slices of real hadith text, with one word substituted or two deleted for near-miss cases); they are not
human-written queries and say nothing about meaning or claim analysis.

  hadith_retrieval     BM25 over hadith_fts: Recall@1/@5, MRR (acceptable = every hadith that contains the
                       same token sequence, since many texts recur verbatim across narrations/collections)
  hadith_matching      full pipeline outcome per case: correct_resolved / correct_ambiguous_repeated_text /
                       near_match_not_attributed / missed; a resolved result that is not the generating hadith
                       is split into "the resolved passage contains the query verbatim" (the edited query
                       happens to be real text elsewhere, or is an ayah quoted inside the hadith) and
                       WRONG (it does not contain it)
  quran_cross_source   Quran cases through the full pipeline: any attributed to a hadith (must be 0)
  not_found            synthetic non-religious sentences through the full pipeline
  terminology          exact lookup of the 10 package terms in short sentences; false hits on non-religious text

usage: backend/.venv/bin/python eval/multi_source_eval.py [--n 200] [--seed 20261002]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.schemas.analyze import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.normalizer import normalize_for_search, tokens
from app.services.rank_fusion import STRATEGIES

DB = ROOT / "data/indexes/tibyan.sqlite3"


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    return {"n": n, "recall@1": round(sum(r == 1 for r in ranks) / n, 4),
            "recall@5": round(sum(1 for r in ranks if r and r <= 5) / n, 4),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--out", default=None, help="result file name under eval/results/")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    p = AnalysisPipeline(Settings(database_path=str(DB)), ROOT, provider=None)
    rh = p.repo_hadith
    # Cases are built from normalize_for_search(original_text) of NUMBERED records only, so the case set is
    # identical whatever search normalization the index uses and whatever unnumbered records are added.
    hadith = [p.repo.get(r[0]) for r in p.repo.conn.execute(
        "SELECT p.id FROM passages p JOIN sources s ON s.id = p.source_id WHERE s.source_type = 'hadith' "
        "AND json_extract(p.metadata_json, '$.hadith_number') IS NOT NULL ORDER BY p.rowid_int")]
    std = {h.id: normalize_for_search(h.original_text).split() for h in hadith}
    long_ = [h for h in hadith if len(std[h.id]) >= 20]
    vocab = sorted({w for h in rng.sample(hadith, 2000) for w in std[h.id]})
    htok = getattr(p, "hadith_tokenize", tokens)      # the tokenizer the hadith index is searched with

    cases = []
    for h in rng.sample(long_, a.n):
        w = std[h.id]
        L = rng.randint(6, 12)
        s = rng.randint(0, len(w) - L)
        cases.append({"category": "partial_verbatim", "query": " ".join(w[s:s + L]), "pid": h.id})
    for h in rng.sample(long_, a.n):
        w = std[h.id]
        L = rng.randint(10, 14)
        s = rng.randint(0, len(w) - L)
        frag = w[s:s + L]
        frag[rng.randrange(L)] = rng.choice(vocab)
        cases.append({"category": "word_substitution", "query": " ".join(frag), "pid": h.id})
    for h in rng.sample(long_, a.n):
        w = std[h.id]
        L = rng.randint(10, 14)
        s = rng.randint(0, len(w) - L)
        frag = w[s:s + L]
        for _ in range(2):
            frag.pop(rng.randrange(1, len(frag) - 1))
        cases.append({"category": "word_deletion", "query": " ".join(frag), "pid": h.id})

    # honorific variants: a slice around «صلى الله عليه وسلم» quoted with the symbol ﷺ, or with it omitted
    hon = "صلى الله عليه وسلم"
    with_hon = [h for h in long_ if hon in " ".join(std[h.id])]
    for cat, repl in (("honorific_symbol", "ﷺ"), ("honorific_omitted", "")):
        for h in rng.sample(with_hon, a.n):
            w = std[h.id]
            i = next(k for k in range(len(w) - 3) if w[k:k + 4] == hon.split())
            s0, e0 = max(0, i - rng.randint(3, 6)), min(len(w), i + 4 + rng.randint(3, 6))
            ref = " ".join(w[s0:e0])
            cases.append({"category": cat, "query": " ".join((ref.replace(hon, repl)).split()), "pid": h.id,
                          "verbatim_ref": ref})

    ranks: dict[str, list] = {}
    prod_ranks: dict[str, list] = {}
    outcomes: dict[str, Counter] = {}
    for c in cases:
        ok = {c["pid"]}
        if c["category"] == "partial_verbatim":
            ok |= {x.id for x in rh.phrase_hits(tokens(c["query"]), limit=1000)}
        if "verbatim_ref" in c:   # every hadith containing the un-edited slice is a correct answer
            ok |= {x.id for x in rh.phrase_hits(tokens(c["verbatim_ref"]), limit=1000)}
        lex = p.lexical_hadith.search(c["query"], k=20)
        ids = [x.passage.id for x in lex]
        ranks.setdefault(c["category"], []).append(next((i + 1 for i, x in enumerate(ids) if x in ok), None))
        # production ranking: verbatim phrase hits first, then BM25 order (lexical_first), top 10
        if hasattr(p, "hadith_candidates"):        # the production ranking function itself
            fused = p.hadith_candidates(c["query"])
        else:                                       # before the function existed: same rule inline
            exact = {x.id for x in rh.phrase_hits(htok(c["query"]))}
            fused = STRATEGIES["lexical_first"](lex, [], k=60, top_n=10, exact_ids=exact)
        fids = [x.passage.id for x in fused]
        prod_ranks.setdefault(c["category"], []).append(next((i + 1 for i, x in enumerate(fids) if x in ok), None))
        r = p.analyze(AnalyzeRequest(quote=c["query"], claim="تقييم"))
        qa = r.quote_analysis
        alts = {u.passage_id for u in qa.alternatives}
        if r.source is not None:
            got = {u.passage_id for u in r.context.matched}
            # does the resolved passage really contain the query verbatim? (checked in its own index)
            # EXACT/PARTIAL results come only from verbatim phrase or (Quran) consecutive-ayat span matches
            verbatim = qa.match_method in ("phrase", "span") and qa.match_status in ("EXACT", "PARTIAL")
            if r.source.source_type != "hadith":
                o = ("resolved_to_quran_query_is_verbatim_ayah_text" if verbatim
                     else "WRONG_CROSS_SOURCE_resolved_to_" + r.source.source_type)
            elif got & ok:
                o = "correct_resolved"
            else:
                o = "resolved_to_other_hadith_containing_query_verbatim" if verbatim else "WRONG_resolved"
        elif qa.match_status == "AMBIGUOUS" and qa.ambiguity_reason == "NEAR_MATCH_UNCONFIRMED":
            o = "near_match_not_attributed_source_listed" if alts & ok else "near_match_not_attributed_source_not_listed"
        elif qa.match_status == "AMBIGUOUS":
            o = "correct_ambiguous_repeated_text" if (alts & ok or qa.alternatives_total > len(alts)) \
                else "ambiguous_source_not_listed"
        else:
            o = "missed"
        outcomes.setdefault(c["category"], Counter())[o] += 1

    # Quran cases through the full multi-source pipeline: none may be attributed to a hadith
    quran = [p.repo.get(r[0]) for r in p.repo.conn.execute(
        "SELECT id FROM passages WHERE source_id = 'quran' ORDER BY rowid_int")]
    qc = Counter()
    for q in rng.sample(quran, a.n):
        w = q.metadata["publisher_aya_text_emlaey"].split()
        L = min(len(w), rng.randint(4, 8))
        s = rng.randint(0, len(w) - L)
        r = p.analyze(AnalyzeRequest(quote=" ".join(w[s:s + L]), claim="تقييم"))
        st = r.source.source_type if r.source else ("ambiguous_" + "+".join(sorted({u.source_type or "?" for u in
                                                                                    r.quote_analysis.alternatives}))
                                                     if r.quote_analysis.match_status == "AMBIGUOUS" else "none")
        qc[st] += 1

    lines = [ln.strip() for ln in (ROOT / "eval/fixtures/synthetic_not_found_ar.txt").read_text(encoding="utf-8")
             .splitlines() if ln.strip() and not ln.startswith("#")]
    nf = Counter()
    term_false = 0
    for ln in lines:
        r = p.analyze(AnalyzeRequest(quote=ln, claim="تقييم"))
        nf[r.quote_analysis.match_status + ("/" + r.quote_analysis.ambiguity_reason
                                            if r.quote_analysis.ambiguity_reason else "")] += 1
        term_false += len(p.terminology.lookup(ln))

    term_hits = Counter()
    for e in p.terminology.entries:
        for tpl in ("ما معنى {t}", "ترجمة كلمة {t}", "و{t} في هذا السياق"):
            found = [x["id"] for x in p.terminology.lookup(tpl.format(t=e["term_ar"]))]
            term_hits["correct" if e["id"] in found else "missed"] += 1

    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "seed": a.seed, "cases_per_category": a.n,
        "corpus_version": p.corpus_version,
        "case_source": "generated from the hadith corpus itself (seeded slices; substitutions from corpus vocabulary)",
        "hadith_search_normalization": getattr(p, "hadith_norm_version", "norm-v1 (same as Quran)"),
        "hadith_retrieval_bm25": {k: metrics(v) for k, v in ranks.items()},
        "hadith_retrieval_production_ranking": {k: metrics(v) for k, v in prod_ranks.items()},
        "hadith_matching_full_pipeline": {k: dict(v) for k, v in outcomes.items()},
        "quran_cases_full_pipeline_by_resolved_source": dict(qc),
        "not_found_synthetic_full_pipeline": {"n": len(lines), "status_counts": dict(nf)},
        "terminology_lookup": {"queries": sum(term_hits.values()), **dict(term_hits),
                               "false_hits_on_non_religious_sentences": term_false},
        "not_measured": ["tafsir, aqeedah, fiqh, history, dawah and shubuhat retrieval (sources not ingested)",
                         "real user hadith quotations, paraphrased hadith, grading questions",
                         "claim analysis on hadith (disabled)"],
    }
    dst = ROOT / "eval/results" / (a.out or "multi_source_eval.json")
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("hadith_search_normalization", "hadith_retrieval_bm25",
                                          "hadith_retrieval_production_ranking", "hadith_matching_full_pipeline",
                                          "quran_cases_full_pipeline_by_resolved_source",
                                          "not_found_synthetic_full_pipeline", "terminology_lookup")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
