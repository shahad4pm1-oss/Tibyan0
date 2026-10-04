"""Shared fixtures.

Two corpora are used:
- SYNTHETIC: built per test session from tests/fixtures (NON-RELIGIOUS Arabic sentences),
  with an APPROVED synthetic source, a PENDING_REVIEW source, a REJECTED source and a
  synthetic hadith-format collection. Semantic tests on it use the HASH TEST DOUBLE.
- REAL: the production corpus built by scripts/build_corpus.py from the verified KFGQPC
  package. Tests marked `real_corpus` are skipped if it has not been built. Real-corpus tests
  never type Quran text: they read text from the database.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

# Tests never read the developer's .env (it may hold a real LLM key); must be set before app imports.
os.environ["TIBYAN_ENV_FILE"] = ""
# Tests never reach the network: the live al-Tabari API is exercised only through a mock transport.
os.environ.setdefault("TAFSIR_PROVIDER", "local")

import faiss
import pytest

from app.corpus.common import (
    PassageRecord,
    SourceRecord,
    insert_passages,
    insert_source,
    link_sequential,
    set_info,
)
from app.corpus.fts import build_fts
from app.corpus.hadith import ingest as ingest_hadith
from app.corpus.validation import original_text_digest
from app.db.connection import connect, init_schema
from app.repositories.corpus import CorpusRepository
from app.services.embeddings import HashEmbedding
from app.services.normalizer import normalize_for_search

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / "data" / "indexes" / "tibyan.sqlite3"


def pytest_configure(config):
    config.addinivalue_line("markers", "real_corpus: needs the production corpus built from the KFGQPC package")


def _src(sid: str, status: str, meta: dict | None = None) -> SourceRecord:
    return SourceRecord(id=sid, source_type="synthetic_fixture", title=f"Synthetic {sid}", edition="test-1",
                        license_note="test fixture", verification_status=status, acquired_at="2026-10-01",
                        corpus_version="test", metadata=meta or {})


def build_synthetic(dirpath: Path) -> Path:
    data = json.loads((FIX / "synthetic_book.json").read_text(encoding="utf-8"))
    db = dirpath / "synthetic.sqlite3"
    conn = connect(db)
    init_schema(conn)
    insert_source(conn, _src("synth", "APPROVED", {"context_policy": "sequential_window"}))
    passages, groups, seq = [], {}, 0
    for ci, chapter in enumerate(data["chapters"], start=1):
        for vi, text in enumerate(chapter, start=1):
            seq += 1
            pid = f"synth:{ci}:{vi}"
            passages.append(PassageRecord(id=pid, source_id="synth", reference=f"{ci}:{vi}", sequence=seq,
                                          parent_id=f"synth:{ci}", original_text=text,
                                          normalized_text=normalize_for_search(text),
                                          metadata={"chapter": ci, "item": vi}))
            groups.setdefault(f"synth:{ci}", []).append(pid)
    insert_passages(conn, passages)
    link_sequential(conn, groups)
    for sid, status, key in (("synth_pending", "PENDING_REVIEW", "pending_chapter"),
                             ("synth_rejected", "REJECTED", "rejected_chapter")):
        insert_source(conn, _src(sid, status))
        insert_passages(conn, [PassageRecord(id=f"{sid}:1", source_id=sid, reference="1", sequence=1,
                                             parent_id=f"{sid}:1", original_text=t,
                                             normalized_text=normalize_for_search(t))
                               for t in data[key]])
    ingest_hadith(conn, FIX / "synthetic_hadith_manifest.json", FIX / "synthetic_hadith.jsonl", "test")
    set_info(conn, "corpus_kind", "test_fixture")
    set_info(conn, "corpus_version", "test-synthetic")
    build_fts(conn, production=False)
    set_info(conn, "original_text_sha256", original_text_digest(conn))
    conn.commit()

    # semantic index with the HASH TEST DOUBLE (APPROVED passages only)
    repo = CorpusRepository(conn)
    rows = conn.execute("""SELECT p.rowid_int, p.normalized_text FROM passages p JOIN sources s ON s.id = p.source_id
                           WHERE s.verification_status = 'APPROVED' ORDER BY p.rowid_int""").fetchall()
    emb = HashEmbedding()
    vecs = emb.embed([r[1] for r in rows])
    idx = faiss.IndexFlatIP(vecs.shape[1])
    idx.add(vecs)
    faiss.write_index(idx, str(dirpath / "semantic.faiss"))
    (dirpath / "semantic_ids.json").write_text(json.dumps([r[0] for r in rows]))
    (dirpath / "semantic_meta.json").write_text(json.dumps({
        "provider": "hash", "model": emb.model_name, "is_test_double": True, "dim": emb.dim,
        "count": len(rows), "original_text_sha256": repo.info["original_text_sha256"]}))
    conn.close()
    return db


@pytest.fixture(scope="session")
def synthetic_db(tmp_path_factory) -> Path:
    return build_synthetic(tmp_path_factory.mktemp("synth"))


@pytest.fixture()
def synthetic_repo(synthetic_db) -> CorpusRepository:
    return CorpusRepository(connect(synthetic_db, readonly=True))


@pytest.fixture()
def synthetic_copy(synthetic_db, tmp_path) -> Path:
    for f in synthetic_db.parent.iterdir():
        shutil.copy(f, tmp_path / f.name)
    return tmp_path / synthetic_db.name


@pytest.fixture(scope="session")
def real_db() -> Path:
    if not REAL_DB.exists():
        pytest.skip("production corpus not built (run scripts/build_corpus.py)")
    return REAL_DB


@pytest.fixture()
def real_repo(real_db) -> CorpusRepository:
    return CorpusRepository(connect(real_db, readonly=True))


@pytest.fixture()
def real_copy(real_db, tmp_path) -> Path:
    dst = tmp_path / "copy.sqlite3"
    shutil.copy(real_db, dst)
    return dst


# ---------------- Phase 3 helpers ----------------
from app.core.config import Settings
from app.llm.test_doubles import ScriptedProvider
from app.schemas.analyze import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline


def make_pipeline(db: Path, script=None, provider="scripted", **settings) -> AnalysisPipeline:
    s = Settings(database_path=str(db), embedding_provider=settings.pop("embedding_provider", "hash"),
                 embedding_model=settings.pop("embedding_model", ""), **settings)
    if provider == "scripted":
        prov = ScriptedProvider(list(script or []))
    else:
        prov = provider
    return AnalysisPipeline(s, db.parent, provider=prov)


def ask(pipe: AnalysisPipeline, quote: str, claim: str):
    return pipe.analyze(AnalyzeRequest(quote=quote, claim=claim))


def good_output(relation="SUPPORTED", ids=("E1",), **over) -> dict:
    out = {"relation": relation, "summary": "يتسق الادعاء مع الدليل المعروض.", "reason": f"{ids[0]} يذكر ذلك صراحة.",
           "evidence_ids": list(ids), "key_evidence": [{"evidence_id": ids[0], "relevance": "يتضمن المعنى المذكور"}],
           "needs_specialist": False, "uncertainty_reason": None}
    if relation in ("INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"):
        out.update(uncertainty_reason="الأدلة لا تحسم المسألة", needs_specialist=relation == "REQUIRES_SPECIALIST")
    out.update(over)
    return out


def good_minimal(verdict="correct", parts=(("الادعاء", "E1: يذكر النص ذلك صراحة في سياقه.", "supported"),)) -> dict:
    """Claim-centric minimal model output (prompt claim_analysis_v2)."""
    return {"verdict": verdict,
            "assertions": [{"claim_part": c, "evidence_context": e, "label": lbl} for c, e, lbl in parts]}


@pytest.fixture()
def real_quote(real_repo):
    """First four words of 2:191 in the publisher's imla'i text, read from the DB (never typed)."""
    return " ".join(real_repo.get("quran:2:191").metadata["publisher_aya_text_emlaey"].split()[:4])


@pytest.fixture()
def synthetic_as_production(synthetic_copy) -> Path:
    """Copy of the synthetic corpus re-marked corpus_kind=production, to test production-mode guards that are
    unrelated to the corpus check (production otherwise refuses a test-fixture corpus)."""
    c = connect(synthetic_copy)
    set_info(c, "corpus_kind", "production")
    # the repository also hides synthetic_fixture sources outside test-fixture corpora (second guard)
    c.execute("UPDATE sources SET source_type = 'quran' WHERE id = 'synth'")
    from app.corpus.fts import build_fts
    build_fts(c, production=True)
    c.commit()
    c.close()
    return synthetic_copy
