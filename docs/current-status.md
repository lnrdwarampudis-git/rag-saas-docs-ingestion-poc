# Current Status And Roadmap

This page is the short handoff for what the POC supports today, how to run it, and what remains to build next. Keep it aligned with [README](../README.md), [Architecture](architecture.md), [Flow Diagrams](flow-diagrams.md), [Model Providers](model-providers.md), [Deployment Hardening](deployment-hardening.md), [Local Model Deployment](local-model-deployment.md), and [Execution Runbook](runbook.md).

## Current Delivered State

- Multi-tenant FastAPI backend with Keycloak OIDC login, JWT validation, and Postgres-backed RBAC.
- React/Vite UI with login, session visibility, document upload, direct upload-session mode, document management, query, model/vector/reranker status, retrieval evaluation, and admin analytics panels.
- Docker Compose stack for backend, frontend, default worker, OCR worker, Postgres/pgvector, Redis, MinIO, Qdrant, and Keycloak.
- Background ingestion through `POST /api/v1/documents/upload-async`, Redis queues, and `python -m app.worker`.
- Configurable upload guardrails for browser uploads: allowed extensions and maximum byte size are enforced by the API and pre-checked in the UI.
- Resumable upload-session API and UI mode for large files with tenant/uploader-bound sessions, filesystem or MinIO part storage, dynamic max-part sizing, presigned MinIO part URLs, browser part progress, async completion, completed-session cleanup, and stale-session cleanup command.
- Processing job status, local run, cancel, and retry controls through `GET /api/v1/processing-jobs/{job_id}`, `POST /api/v1/processing-jobs/{job_id}/run`, `POST /api/v1/processing-jobs/{job_id}/cancel`, and `POST /api/v1/processing-jobs/{job_id}/retry`.
- Tenant-scoped document inventory, chunk preview, query pipeline, citations, Redis query cache, and cache/model-aware query metrics.
- Offline retrieval quality gate through `python -m app.eval.run` and authenticated UI/API evaluation status, including no-answer, RBAC-denial, tenant-isolation, and answer-groundedness checks.
- Admin analytics for documents, jobs, durable job-event history, query volume/cache/latency, p95/recent latency, model latency detail tables, vector/reranker retrieval state, Qdrant live collection health with payload-index diagnostics, audit operations, audit filtering, evaluation health, persisted evaluation trend history, and configurable retention cleanup for persisted ops history.
- Local/open-source model abstraction with deterministic hashing embeddings and extractive answer generation as defaults.
- Optional Ollama embeddings and answer generation for local models, including tested Mac-host Ollama access from Docker through `host.docker.internal`.
- Vector index abstraction with in-memory default, pgvector and Qdrant adapter paths, vector backfill command, model-status readiness checks, analytics warning thresholds, default no-op reranker, and deterministic local keyword reranker.
- Container-packaged OCR for images and scanned/image-backed PDFs using Tesseract plus PyMuPDF page rendering.
- Parser/OCR extraction warnings returned by ingest APIs, persisted in document metadata, and surfaced in document inventory/detail UI.
- Extraction duration, OCR duration, and OCR page counts returned by ingest APIs, persisted in document metadata, and surfaced in document detail UI.

## Recently Completed Ops Extensions

- Large-file ingestion ops now include the React `Upload session` action, tenant/uploader-bound resumable sessions, filesystem or MinIO part storage, dynamic part sizing through `UPLOAD_SESSION_PART_BYTES` plus `UPLOAD_SESSION_MAX_PARTS`, direct browser-to-MinIO presigned uploads, completed-session cleanup, stale-session cleanup, MinIO lifecycle policy automation, `MINIO_PUBLIC_ENDPOINT` for browser-reachable presigned URLs, and local MinIO CORS setup guidance.
- Persistent vector retrieval operations now include pgvector and Qdrant adapter paths, vector ops check/backfill automation, Qdrant payload indexes for RBAC filter fields, vector backend metrics in query responses, vector-index readiness in `/api/v1/model-status`, retrieval backend/reranker warning state in `/api/v1/analytics`, and documented production checks after backend/model changes.
- Stronger local model foundations now include packaged profiles (`local-default`, `host-ollama`, `compose-ollama`, `vllm-gpu`), Ollama and vLLM-compatible embedding/answer-generation paths, model-status checks for embedding/answer/vector/reranker runtimes, deterministic local keyword reranking, HTTP-backed cross-encoder/vLLM reranking, latency warning threshold config, and UI surfaces for active model, profile, vector, reranker, and threshold state.
- Operations controls now include queued/processing job cancel, failed-job retry history, Redis dead-letter queue routing after `PROCESSING_JOB_MAX_ATTEMPTS`, `WORKER_MAX_JOBS_PER_RUN` for supervised/batch workers, job cancel audit events, and `GET /api/v1/analytics?action=...&resource_type=...` audit filtering.
- Deployment hardening now includes a GitHub Actions CI workflow, production Compose overlay example, Kubernetes starter manifest, VM/systemd starter services and timer, Render starter blueprint with retention cron, Fly.io process-group starter, ECS/Fargate task and service starters, production environment checklist, deployment hardening guide, backup/restore runbook, expanded evaluation gate, persisted evaluation trend records, durable job/model latency history tables, Qdrant live health with payload-index diagnostics, and local GPU/vLLM deployment examples.

## Supported Document Intake Today

| Format | Status | Notes |
| --- | --- | --- |
| PDF | Supported | Native text extraction first; OCR fallback renders scanned/image-backed pages and sends them to Tesseract. |
| DOCX | Supported | Extracts paragraphs from modern Word documents. |
| XLSX | Supported | Extracts sheet names and cell values with formulas resolved to stored values. |
| PPTX | Supported | Extracts slide text from modern PowerPoint files. |
| TXT, Markdown | Supported | Reads UTF-8 text directly. |
| CSV, TSV | Supported | Reads text directly for chunking and retrieval. |
| PNG, JPG/JPEG, TIFF, BMP | Supported with OCR | Uses Tesseract through `pytesseract`; local machines/containers must have the Tesseract binary available for real OCR. |
| DOC, XLS, PPT | Not supported directly | Convert legacy binary Office files to DOCX, XLSX, or PPTX first. |

OCR is wired in the parser layer and can be forced from the API/UI with `force_ocr`. The backend Docker image includes Tesseract, English OCR data, PyMuPDF, and Pillow so image OCR and scanned-PDF OCR work in containers. Additional Tesseract language packs can be added through `Dockerfile.backend` and selected with `OCR_LANGUAGE`. If OCR dependencies are missing in a local non-Docker environment, extraction records a warning and returns empty OCR text rather than crashing the whole app path.

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
OCR_LANGUAGE=eng
OCR_PDF_DPI=200
OCR_MAX_PDF_PAGES=20
PROCESSING_QUEUE_NAME=rag:processing-jobs
OCR_PROCESSING_QUEUE_NAME=rag:processing-jobs:ocr
WORKER_QUEUE_NAMES=rag:processing-jobs,rag:processing-jobs:ocr
WORKER_MAX_JOBS_PER_RUN=0
PROCESSING_DEAD_LETTER_QUEUE_NAME=rag:processing-jobs:dead-letter
PROCESSING_JOB_MAX_ATTEMPTS=3
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
LOCAL_MODEL_PROFILE=custom
LOCAL_MODEL_GPU_PROFILE=none
PUBLIC_LLM_ENABLED=false
```

Packaged local profiles can replace the individual runtime values when you want a known local deployment target:

```text
LOCAL_MODEL_PROFILE=local-default   # hashing + extractive defaults
LOCAL_MODEL_PROFILE=host-ollama     # Docker backend/worker -> Mac Ollama
LOCAL_MODEL_PROFILE=compose-ollama  # backend/worker -> Compose ollama service
LOCAL_MODEL_PROFILE=vllm-gpu        # OpenAI-compatible vLLM endpoints plus local reranker
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

1. Add public/token LLM providers only after policy approval and explicit `PUBLIC_LLM_ENABLED=true`.

Public token-based LLM providers remain intentionally deferred. They should stay behind explicit provider configuration and `PUBLIC_LLM_ENABLED=true`.
