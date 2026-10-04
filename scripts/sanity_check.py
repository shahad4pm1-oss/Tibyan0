"""Post-setup sanity check: loads the real corpus and runs one Quran and one hadith lookup locally.

No network access and no LLM are used. Exit code 1 on any failure. Output is ASCII-only so it prints
safely in any Windows console.

usage: python scripts/sanity_check.py
"""

from __future__ import annotations

import sys

from _common import ROOT

from app.core.config import get_settings
from app.schemas.analyze import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline, CorpusNotAvailable


def main() -> int:
    s = get_settings()
    try:
        p = AnalysisPipeline(s, ROOT)
    except CorpusNotAvailable as e:
        print(f"FAIL: corpus not available: {e}")
        return 1
    counts = p.repo.count_by_type()
    print(f"corpus {p.corpus_version}: quran={counts.get('quran', 0)} hadith={counts.get('hadith', 0)} "
          f"integrity_ok={p.corpus_integrity_ok}")
    print(f"semantic index: {'ready' if p.semantic.available else 'NOT READY (' + str(p.semantic.reason) + ')'}")
    llm = "REAL_LLM" if p.llm is not None and not p.llm.is_test_double else (
        "LLM_UNAVAILABLE" if p.llm is None else "TEST_DOUBLE_NON_PRODUCTION")
    print(f"llm mode: {llm}")
    ok = counts.get("quran") == 6236 and counts.get("hadith", 0) > 10000 and p.corpus_integrity_ok

    q = p.repo.get("quran:1:2").metadata["publisher_aya_text_emlaey"]          # read from the DB, not typed
    r = p.analyze(AnalyzeRequest(quote=q, claim="sanity check"))
    good = r.quote_analysis.match_status == "EXACT" and r.source and r.source.reference == "1:2"
    print(f"quran lookup: {r.quote_analysis.match_status} {r.source.source_id + ' ' + r.source.reference if r.source else '-'}"
          f" -> {'OK' if good else 'FAIL'}")
    ok = ok and good

    words = p.repo.get("hadith:bukhari:7563").original_text.split()[-12:]
    r = p.analyze(AnalyzeRequest(quote=" ".join(words), claim="sanity check"))
    good = r.source is not None and r.source.source_id == "hadith:bukhari"
    print(f"hadith lookup: {r.quote_analysis.match_status} {r.source.source_id + ' ' + r.source.reference if r.source else '-'}"
          f" -> {'OK' if good else 'FAIL'}")
    ok = ok and good
    if llm == "LLM_UNAVAILABLE":
        good = r.claim_analysis.summary_source != "ai" and r.claim_analysis.attempts == 0
        print(f"no-LLM mode: no AI verdict produced -> {'OK' if good else 'FAIL'}")
        ok = ok and good
    print("SANITY CHECK PASSED" if ok else "SANITY CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
