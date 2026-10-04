"""Compare BM25-only vs semantic-only vs hybrid retrieval on known-answer cases.

Cases are GENERATED programmatically from the real corpus (no text typed by hand):
each case starts from a real passage and applies a documented transformation.
Expected answers are therefore known. Generated cases are NOT human paraphrases and
are NOT expert-reviewed; see docs/METHODOLOGY.md for what this does and does not show.

Also measures end-to-end quote matching on the same cases and the NOT_FOUND
false-positive rate on synthetic non-religious sentences.

usage: python eval/compare_retrieval.py [--n 200] [--seed 20261001]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.db.connection import connect
from app.repositories.corpus import CorpusRepository
from app.services.lexical_retriever import LexicalRetriever
from app.services.normalizer import tokens
from app.services.quote_matcher import QuoteMatcher
from app.services.rank_fusion import lexical_first, rrf
from app.services.semantic_retriever import SemanticRetriever

CATEGORIES = ["exact_uthmani", "exact_imlaei", "partial", "formatting", "span", "word_substitution",
              "word_deletion"]


def emlaey(p):
    return p.metadata["publisher_aya_text_emlaey"].split()


def gen_cases(repo: CorpusRepository, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    # Quran retrieval evaluation: Quran passages only (hadith are evaluated by eval/multi_source_eval.py)
    allp = [repo.get(r[0]) for r in repo.conn.execute(
        "SELECT p.id FROM passages p JOIN sources s ON s.id = p.source_id WHERE s.source_type = 'quran' "
        "ORDER BY p.rowid_int")]
    long_ = [p for p in allp if len(emlaey(p)) >= 10]
    vocab = sorted({w for p in allp for w in emlaey(p)})
    cases = []

    def add(cat, q, pid, extra=None):
        cases.append({"category": cat, "query": q, "source_passage": pid, **(extra or {})})

    for p in rng.sample(allp, n):
        add("exact_uthmani", p.original_text, p.id)
    for p in rng.sample(allp, n):
        add("exact_imlaei", " ".join(emlaey(p)), p.id)
    for p in rng.sample(long_, n):
        w = emlaey(p); L = rng.randint(4, 8); s = rng.randint(0, len(w) - L)
        add("partial", " ".join(w[s:s + L]), p.id, {"slice": [s, L]})
    for p in rng.sample(long_, n):
        w = emlaey(p); L = rng.randint(5, 9); s = rng.randint(0, len(w) - L)
        frag = "  ".join(w[s:s + L])
        add("formatting", f"﴿ {frag} ﴾ ({p.metadata['ayah_number']})", p.id, {"slice": [s, L]})
    spans = 0
    for p in rng.sample(long_, len(long_)):
        nxt = repo.neighbor(p.id, "next")
        if not nxt or len(emlaey(nxt)) < 4:
            continue
        k1, k2 = rng.randint(3, 5), rng.randint(3, 5)
        q = " ".join(emlaey(p)[-k1:] + emlaey(nxt)[:k2])
        add("span", q, p.id, {"span_with": nxt.id})
        spans += 1
        if spans >= n:
            break
    for p in rng.sample(long_, n):
        w = emlaey(p); L = min(len(w), rng.randint(8, 12)); s = rng.randint(0, len(w) - L)
        frag = w[s:s + L]; i = rng.randrange(L); frag[i] = rng.choice(vocab)
        add("word_substitution", " ".join(frag), p.id, {"slice": [s, L], "replaced_index": i})
    for p in rng.sample(long_, n):
        w = emlaey(p); L = min(len(w), rng.randint(9, 12)); s = rng.randint(0, len(w) - L)
        frag = w[s:s + L]
        for _ in range(2):
            frag.pop(rng.randrange(1, len(frag) - 1))
        add("word_deletion", " ".join(frag), p.id, {"slice": [s, L], "deleted": 2})
    return cases


def acceptable(repo: CorpusRepository, case: dict) -> set[str]:
    """Correct answers: the source passage, plus (for verbatim cases) every passage that
    contains the same token sequence, since repeated wording is genuinely ambiguous."""
    ok = {case["source_passage"]}
    if case.get("span_with"):
        ok.add(case["span_with"])
    if case["category"] in ("exact_uthmani", "exact_imlaei", "partial", "formatting"):
        ok |= {p.id for p in repo.phrase_hits(tokens(case["query"]))}
    return ok


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    return {
        "n": n,
        "recall@1": round(sum(1 for r in ranks if r == 1) / n, 4),
        "recall@5": round(sum(1 for r in ranks if r and r <= 5) / n, 4),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 4),
    }


def first_rank(ids: list[str], ok: set[str]) -> int | None:
    return next((i + 1 for i, x in enumerate(ids) if x in ok), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--db", default=str(ROOT / "data/indexes/tibyan.sqlite3"))
    a = ap.parse_args()
    s = Settings()
    repo = CorpusRepository(connect(a.db, readonly=True))
    lex = LexicalRetriever(repo, 20)
    sem = SemanticRetriever(repo, Path(a.db).parent, s.embedding_provider, s.embedding_model, s.app_env, 20)
    if not sem.available:
        print("semantic retrieval unavailable:", sem.reason)
        return 1
    matcher = QuoteMatcher(repo, s.min_partial_tokens, s.max_span_ayat, s.paraphrase_min_coverage,
                           s.paraphrase_min_margin, paraphrase_mode="disabled")  # production behaviour
    matcher_exp = QuoteMatcher(repo, s.min_partial_tokens, s.max_span_ayat, s.paraphrase_min_coverage,
                               s.paraphrase_min_margin, paraphrase_mode="experimental")  # reference only

    cases = gen_cases(repo, a.n, a.seed)
    systems = {"bm25_only": [], "semantic_only": [], "hybrid_rrf": [], "hybrid_rrf_exact_priority": [],
               "hybrid_lexical_first": []}
    by_cat = defaultdict(lambda: defaultdict(list))
    match_by_cat = defaultdict(Counter)
    match_correct = defaultdict(Counter)
    for c in cases:
        ok = acceptable(repo, c)
        L = lex.search(c["query"])
        S = sem.search(c["query"])
        exact = {p.id for p in repo.phrase_hits(tokens(c["query"]))}
        lists = {
            "bm25_only": [x.passage.id for x in L],
            "semantic_only": [x.passage.id for x in S],
            "hybrid_rrf": [x.passage.id for x in rrf(L, S, k=s.rrf_k, top_n=20)],
            "hybrid_rrf_exact_priority": [x.passage.id for x in rrf(L, S, k=s.rrf_k, top_n=20, exact_ids=exact)],
            "hybrid_lexical_first": [x.passage.id for x in lexical_first(L, S, k=s.rrf_k, top_n=40, exact_ids=exact)],
        }
        for name, ids in lists.items():
            r = first_rank(ids, ok)
            systems[name].append(r)
            by_cat[c["category"]][name].append(r)
        lf = lexical_first(L, S, k=s.rrf_k, top_n=10, exact_ids=exact)
        for pool_name, pool, mt in (("production_lexical_first", lf, matcher),
                                    ("hybrid_rrf", rrf(L, S, k=s.rrf_k, top_n=10, exact_ids=exact), matcher),
                                    ("bm25_only", L[:10], matcher),
                                    ("REFERENCE_experimental_paraphrase_on", lf, matcher_exp)):
            m = mt.match(c["query"], pool)
            resolved_ids = {p.id for p in m.passages}
            if m.passages and resolved_ids & ok:
                outcome = "correct_resolved"
            elif m.passages:
                outcome = "WRONG_resolved"
            elif m.status.value == "AMBIGUOUS" and len(ok) > 1:
                outcome = "correct_ambiguous_repeated_text"
            elif m.status.value == "AMBIGUOUS" and m.reason and m.reason.value == "NEAR_MATCH_UNCONFIRMED" \
                    and {p.id for p in m.alternatives} & ok:
                outcome = "near_match_not_attributed_source_listed"
            elif m.status.value == "AMBIGUOUS" and {p.id for p in m.alternatives} & ok:
                outcome = "conservative_ambiguous_source_in_alternatives"
            else:
                outcome = "missed"
            match_correct[(pool_name, c["category"])][outcome] += 1
            if pool_name == "production_lexical_first":
                match_by_cat[c["category"]][m.status.value] += 1

    # NOT_FOUND false positives on synthetic non-religious text
    lines = [ln.strip() for ln in (ROOT / "eval/fixtures/synthetic_not_found_ar.txt").read_text(encoding="utf-8")
             .splitlines() if ln.strip() and not ln.startswith("#")]
    nf = Counter()
    for q in lines:
        L, S = lex.search(q), sem.search(q)
        nf[matcher.match(q, lexical_first(L, S, k=s.rrf_k, top_n=10)).status.value] += 1

    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus_version": repo.info.get("corpus_version"),
        "embedding_model": sem.model_label,
        "rrf_k": s.rrf_k,
        "seed": a.seed,
        "cases_total": len(cases),
        "case_source": "generated from real KFGQPC corpus by documented transformations; not human-written, not expert-reviewed",
        "overall": {k: metrics(v) for k, v in systems.items()},
        "by_category": {cat: {k: metrics(v) for k, v in d.items()} for cat, d in by_cat.items()},
        "quote_matching_status_counts_production": {cat: dict(match_by_cat[cat]) for cat in CATEGORIES},
        "quote_matching_outcomes_by_pool": {
            pool: {cat: dict(match_correct[(pool, cat)]) for cat in CATEGORIES}
            for pool in ("production_lexical_first", "hybrid_rrf", "bm25_only",
                         "REFERENCE_experimental_paraphrase_on")},
        "paraphrase_mode_production": "disabled",
        "not_found_synthetic": {"n": len(lines), "status_counts": dict(nf),
                                "false_positive_rate": round(1 - nf.get("NOT_FOUND", 0) / len(lines), 4)},
    }
    res_dir = ROOT / "eval/results"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "retrieval_comparison.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
