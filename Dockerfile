# Tibyan backend image (FastAPI + SQLite FTS5 + FAISS). No LLM key is baked in; the app runs in
# LLM_UNAVAILABLE mode until LLM_PROVIDER / LLM_MODEL / LLM_API_KEY are set in the host's secret store.
#
# The corpus is built at image build time from the publisher package (scripts/fetch_quran.py verifies
# the pinned SHA-256 and refuses any other file), then validated (V01-V13). The build fails if validation fails.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/requirements.txt backend/constraints.txt backend/
RUN pip install -r backend/requirements.txt -c backend/constraints.txt

COPY backend/app backend/app
COPY backend/pyproject.toml backend/pyproject.toml
COPY scripts scripts
COPY data/metadata data/metadata
COPY data/curated data/curated
COPY data/json-data data/json-data
COPY eval/results eval/results
RUN mkdir -p data/raw data/indexes && python scripts/build_corpus.py

RUN useradd --system --uid 10001 tibyan && chown -R tibyan /app/data/indexes
USER tibyan

ENV APP_ENV=production PORT=8000
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health',timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --no-server-header"]
