# Current Status And Roadmap

This page is the short handoff for what the POC supports today, how to run it, and what remains to build next. Keep it aligned with [README](../README.md), [Architecture](architecture.md), [Flow Diagrams](flow-diagrams.md), [Model Providers](model-providers.md), and [Execution Runbook](runbook.md).

## Current Delivered State

- Multi-tenant FastAPI backend with Keycloak OIDC login, JWT validation, and Postgres-backed RBAC.
- React/Vite UI with login, session visibility, document upload, document management, query, model status, retrieval evaluation, and admin analytics panels.
- Docker Compose stack for backend, frontend, worker, Postgres/pgvector, Redis, MinIO, Qdrant, and Keycloak.
- Background ingestion through `POST /api/v1/documents/upload-async`, Redis queue, and `python -m app.worker`.
- Configurable upload guardrails for browser uploads: allowed extensions and maximum byte size are enforced by the API and pre-checked in the UI.
- Processing job status, local run, and retry controls through `GET /api/v1/processing-jobs/{job_id}`, `POST /api/v1/processing-jobs/{job_id}/run`, and `POST /api/v1/processing-jobs/{job_id}/retry`.
- Tenant-scoped document inventory, chunk preview, query pipeline, citations, Redis query cache, and cache/model-aware query metrics.
- Offline retrieval quality gate through `python -m app.eval.run` and authenticated UI/API evaluation status.
- Admin analytics for documents, jobs, query volume/cache/latency, audit operations, and evaluation health.
- Local/open-source model abstraction with deterministic hashing embeddings and extractive answer generation as defaults.
- Optional Ollama embeddings and answer generation for local models, including tested Mac-host Ollama access from Docker through `host.docker.internal`.

## Supported Document Intake Today

| Format | Status | Notes |
| --- | --- | --- |
| PDF | Supported | Native text extraction first; OCR fallback when extracted text is empty or `force_ocr=true`. |
| DOCX | Supported | Extracts paragraphs from modern Word documents. |
| XLSX | Supported | Extracts sheet names and cell values with formulas resolved to stored values. |
| PPTX | Supported | Extracts slide text from modern PowerPoint files. |
| TXT, Markdown | Supported | Reads UTF-8 text directly. |
| CSV, TSV | Supported | Reads text directly for chunking and retrieval. |
| PNG, JPG/JPEG, TIFF, BMP | Supported with OCR | Uses Tesseract through `pytesseract`; local machines/containers must have the Tesseract binary available for real OCR. |
| DOC, XLS, PPT | Not supported directly | Convert legacy binary Office files to DOCX, XLSX, or PPTX first. |

OCR is wired in the parser layer and can be forced from the API/UI with `force_ocr`. If Tesseract is not installed, OCR extraction records a warning and returns empty OCR text rather than crashing the whole app path.

## Default Execution Path

```bash
cp .env.example .env
docker compose up -d --build
```

Open the UI at `http://127.0.0.1:5173`, sign in with a demo user, upload or queue a document, wait for ingestion to finish, and ask a question.

Browser uploads are capped at 512 MiB by default. Tune these values in `.env` when needed:

```text
MAX_UPLOAD_BYTES=536870912
ALLOWED_UPLOAD_EXTENSIONS=.pdf,.txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.bmp
```

Demo users all use password `Passw0rd!`:

- `admin-demo`
- `finance-demo`
- `engineer-demo`
- `legal-demo`
- `support-demo`

## Local Model Modes

The default mode is deterministic and requires no model download:

```text
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_RUNTIME=hashing
LOCAL_EMBEDDING_MODEL_NAME=hashing-384
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
PUBLIC_LLM_ENABLED=false
```

To use Ollama running on the Mac while backend/worker run in Docker:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text:latest
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1:8b
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

Then restart:

```bash
docker compose up -d --build backend worker
```

To run Ollama inside Docker Compose, start the optional profile and point backend/worker to `http://ollama:11434`; see [Model Providers](model-providers.md#running-ollama-in-docker-compose).

## Validation Checklist

Run these before committing platform changes:

```bash
python3 -m ruff check app tests
env LOCAL_EMBEDDING_RUNTIME=hashing LOCAL_EMBEDDING_MODEL_NAME=hashing-384 LOCAL_LLM_RUNTIME=extractive LOCAL_LLM_MODEL_NAME=extractive python3 -m pytest
env LOCAL_EMBEDDING_RUNTIME=hashing LOCAL_EMBEDDING_MODEL_NAME=hashing-384 LOCAL_LLM_RUNTIME=extractive LOCAL_LLM_MODEL_NAME=extractive python3 -m app.eval.run
cd frontend
npm run build
cd ..
docker compose config
git diff --check
```

## Pending Work

Recommended next implementation slices:

1. Harden ingestion for large files: direct-to-object-storage multipart uploads, upload progress, resumable upload behavior, and object-storage lifecycle cleanup. Basic API/UI size and extension limits are now in place.
2. Add production-grade parser/OCR packaging: container-level Tesseract installation, OCR language configuration, stronger scanned-PDF handling, and parser warnings surfaced in the UI.
3. Persist vector retrieval beyond the current POC baseline: pgvector/Qdrant write/read integration for embeddings, migration checks, and tenant-safe vector filtering.
4. Add reranking and stronger local model options: local cross-encoder or reranker adapter, vLLM adapter path, model health dashboards, and performance thresholds.
5. Improve operations controls: job cancel/retry history, dead-letter queue, worker concurrency controls, and richer audit event filtering.
6. Add deployment hardening: environment-specific Compose/prod manifests, secrets handling, backup/restore runbooks, and CI quality gates.
7. Expand evaluation: more tenant/role fixtures, answer-groundedness checks, negative/no-answer cases, and regression trend history.

Public token-based LLM providers remain intentionally deferred. They should stay behind explicit provider configuration and `PUBLIC_LLM_ENABLED=true`.
