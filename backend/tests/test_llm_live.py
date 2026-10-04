"""LIVE provider tests. Run only when TIBYAN_LIVE_LLM=1 and LLM_PROVIDER/LLM_MODEL/LLM_API_KEY are set.
Status in the build environment: BLOCKED_BY_LLM_ACCESS (no API key)."""

import os

import pytest

from app.core.config import Settings
from app.llm.factory import build_provider

pytestmark = pytest.mark.skipif(os.environ.get("TIBYAN_LIVE_LLM") != "1", reason="BLOCKED_BY_LLM_ACCESS: no live key")


@pytest.mark.real_corpus
def test_live_grounded_output_validates(real_db, real_quote):
    from .conftest import ask, make_pipeline
    prov = build_provider(Settings()).provider
    assert prov is not None and not prov.is_test_double
    p = make_pipeline(real_db, provider=prov, embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, real_quote, "الآية تأمر بقتل غير المسلمين مطلقا")
    assert r.claim_analysis.status in ("COMPLETED", "ABSTAINED", "REFERRED", "AI_OUTPUT_REJECTED")
