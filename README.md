# RAG SaaS Docs Ingestion POC

Open-source proof of concept for a multi-tenant SaaS RAG document ingestion and query workflow. It handles browser file upload, PDF and Microsoft Office text extraction, OCR-ready parsing, chunking, RBAC-aware retrieval, Redis query caching, Postgres persistence, visible A&A/session management surfaces, and a React/Vite UI.

The milestone targets are:

- Week 1: database setup, document ingestion foundations, OCR-aware text extraction, and chunking strategies for a multi-tenant RAG SaaS that can scale toward approximately 1 TB of Microsoft Office, PDF, and image-backed documents.
- Week 2: RAG pipeline creation, Redis query caching, retrieval interface, citation output, and API contracts for the Week 3 UI.
- Week 3: React/Vite UI for document ingestion, role-aware querying, citations, cache status, and latency metrics.
- Week 4: Docker containerization plus unit, API E2E, and frontend E2E test coverage.
- Week 5: Keycloak OIDC login (Authorization Code + PKCE), JWT validation middleware, Postgres-backed RBAC, and stateless-JWT session management.
- Week 6: background document ingestion with queued upload, Redis worker polling, processing job status APIs, and UI job status polling.
- Week 7: retrieval evaluation, precision thresholds, and local/open-source model strategy.

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

- UI: `http://127.0.0.1:5173`
- Backend health: `http://127.0.0.1:8000/health`

Sign in with a demo user (all use password `Passw0rd!`): `admin-demo`,
`finance-demo`, `engineer-demo`, `legal-demo`, or `support-demo`. Tenant and
roles come from Keycloak/Postgres, not a manual UI field. See
[Setup Guide](docs/setup.md#signing-in-keycloak) for details.

Optional local models can run in Docker Compose:

```bash
docker compose --profile local-models up -d ollama
```

See [Model Providers](docs/model-providers.md#running-ollama-in-docker-compose) for model pulls and `.env` settings.

If Ollama already runs on your Mac and the app runs in Docker, use `host.docker.internal`:

```text
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

See [Model Providers](docs/model-providers.md#tested-host-ollama-docker-settings) and [Execution Runbook](docs/runbook.md#mac-host-ollama-container-check) for the tested setup.

For full setup, execution, test, and GitHub export instructions, see:

- [Setup Guide](docs/setup.md)
- [Current Status And Roadmap](docs/current-status.md)
- [Architecture Diagram](docs/architecture.md)
- [Flow Diagrams](docs/flow-diagrams.md)
- [Retrieval Evaluation](docs/retrieval-evaluation.md)
- [Model Providers](docs/model-providers.md)
- [Execution Runbook](docs/runbook.md)
- [GitHub Export Guide](docs/github-export.md)
- [Week 6 Suggested Target Plan](docs/week6-plan.md)
- [Week 7 Suggested Target Plan](docs/week7-plan.md)

## Scope Delivered

- FastAPI backend skeleton
- PostgreSQL schema with RBAC, tenants, documents, chunks, processing jobs, and audit logs
- pgvector-ready chunk table for embeddings
- Qdrant service included for higher-scale vector retrieval experiments
- Redis, MinIO, PostgreSQL, Qdrant, Keycloak, default worker, and OCR worker in Docker Compose
- OCR-aware parser abstraction
- Recursive token-aware chunking with metadata propagation
- Role-aware chunk metadata model
- Unit tests for chunking and metadata behavior
- Week 1 implementation plan and acceptance checklist
- Week 2 query pipeline with Redis-backed cache fallback
- RBAC-aware hybrid retrieval baseline
- Citation and latency metrics in query responses
- Per-query UI run details for cache outcome, contexts used, model runtimes, thresholds, and latency
- Model runtime status endpoint and UI indicator for hashing/extractive versus Ollama readiness
- Week 3 React/Vite operational UI
- Week 4 backend/frontend Dockerfiles and Compose wiring
- API E2E and frontend Playwright smoke tests
- Visible A&A and session management panels for the POC workflow
- Keycloak OIDC login (Authorization Code + PKCE), JWT validation middleware, and stateless-JWT session management with silent refresh
- Server-side RBAC resolved from Postgres (`app_users`/`roles`/`user_roles`), with tenant_id/roles always taken from the validated token -- never from request bodies
- PDF, Word DOCX, Excel XLSX, PowerPoint PPTX, text, CSV/TSV, markdown, image intake, and scanned-PDF OCR
- Document management inventory with authorized list/detail APIs, ingestion status, visibility, OCR flags, chunk counts, and chunk preview
- Week 6 background ingestion path with queued upload, Redis-backed worker polling, processing job status/retry APIs, and UI job polling
- Week 7 offline retrieval evaluation dataset and runner with context precision, context recall, and answer relevance checks
- Authenticated retrieval evaluation API and UI quality gate panel
- Local/open-source model provider abstraction for deterministic hashing embeddings, optional Ollama embeddings, extractive answer generation, and optional Ollama answer generation, with later adapter paths for vLLM and gated public providers
- Authenticated admin analytics API and UI summary for document ingestion, processing jobs, persisted query cache/latency, recent audit operations, and retrieval evaluation health

## Recommended Week 1 Commands

```bash
cp .env.example .env
docker compose up -d postgres redis minio qdrant keycloak
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

## Frontend Commands

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/health` to `http://127.0.0.1:8000`.

## Week 4 Commands

```bash
python3 -m pytest

cd frontend
npm install
npm run build
npx playwright install chromium
npm run test:e2e

cd ..
docker compose up --build
```

## API Surface

- `GET /health`
- `GET /api/v1/auth/config`
- `GET /api/v1/auth/me`
- `GET /api/v1/documents`
- `POST /api/v1/documents/ingest`
- `POST /api/v1/documents/upload`
- `POST /api/v1/documents/upload-async`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `POST /api/v1/documents/upload-sessions`
- `GET /api/v1/documents/upload-sessions/{upload_session_id}`
- `PUT /api/v1/documents/upload-sessions/{upload_session_id}/parts/{part_number}`
- `POST /api/v1/documents/upload-sessions/{upload_session_id}/parts/{part_number}/presign`
- `POST /api/v1/documents/upload-sessions/{upload_session_id}/parts/{part_number}/complete`
- `POST /api/v1/documents/upload-sessions/{upload_session_id}/complete`
- `GET /api/v1/processing-jobs/{job_id}`
- `POST /api/v1/processing-jobs/{job_id}/run`
- `POST /api/v1/processing-jobs/{job_id}/retry`
- `GET /api/v1/evaluation/retrieval`
- `GET /api/v1/model-status`
- `GET /api/v1/analytics`
- `POST /api/v1/query`

The document list/detail endpoints power the UI's Document Management panel. They apply the same tenant and RBAC rules as retrieval: users can inspect only documents and chunks their authenticated identity is authorized to see.

The analytics endpoint powers the UI's Admin operations summary. It returns tenant-scoped document counts, processing job counts and recent failures, recent persisted query volume/cache/latency metrics, recent audit operations, and the current retrieval quality gate summary.

Successful query requests also write `query.executed` audit events with safe metadata such as query hash, query length, cache state, latency, contexts used, models, and cited document ids. Raw query text is not stored in the audit log.

The ingestion endpoint accepts a local file path for Week 1 development. Production upload should stream files into MinIO first, then enqueue parsing and chunking workers.

The upload endpoint accepts multipart browser uploads and is the preferred local SaaS-style flow because it does not require Docker path mapping.

Browser uploads are guarded by configurable extension and size limits. Defaults are `ALLOWED_UPLOAD_EXTENSIONS=.pdf,.txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.bmp` and `MAX_UPLOAD_BYTES=536870912` (512 MiB). Unsupported formats return `415`; oversized files return `413`.

The async upload endpoint returns `202 Accepted` with a `job_id` and `document_id`. The resumable upload-session endpoints create a session, upload numbered parts, inspect uploaded parts, and complete the session into the same async processing queue. Sessions are bound to the tenant and uploader subject. By default parts use local filesystem storage under `UPLOAD_DIR`; `UPLOAD_SESSION_STORAGE_BACKEND=minio` stores parts in MinIO and exposes presigned part URLs for direct browser-to-object-storage uploads. Docker Compose includes a default `worker` service for normal ingestion and a `worker-ocr` service for forced OCR jobs. Both poll Redis, process queued files, update `processing_jobs`, and transition documents from `pending` to `embedded` or `failed`. Failed jobs can be retried through the processing job retry API or the UI retry action.

Completed upload sessions remove temporary part storage after the final file is assembled. Abandoned sessions can be cleaned up with `python -m app.rag.cleanup_upload_sessions --max-age-hours 24`.

Supported POC intake formats:

- PDF
- Word DOCX
- Excel XLSX
- PowerPoint PPTX
- TXT, Markdown, CSV, TSV
- PNG, JPG/JPEG, TIFF, BMP through OCR
- Scanned/image-backed PDFs through PyMuPDF page rendering plus Tesseract OCR

The backend image installs English OCR data by default. Additional Tesseract language packs can be added in `Dockerfile.backend` and selected with `OCR_LANGUAGE`, for example `OCR_LANGUAGE=eng+spa` when both packs are installed.

Legacy binary Office formats such as DOC, XLS, and PPT should be converted to DOCX, XLSX, or PPTX before ingestion.

The Dockerized frontend nginx proxy allows uploads up to `2g` via `client_max_body_size`. The React UI shows upload progress for browser uploads. Production deployments should prefer `UPLOAD_SESSION_STORAGE_BACKEND=minio` with presigned part URLs and object lifecycle cleanup for very large files.

## Document Management UI

After login, the frontend shows:

- A&A and session management panels so the resolved tenant, roles, token expiry, and refresh behavior are visible.
- Format intake guidance for PDF, DOCX, XLSX, PPTX, text/CSV/markdown, and image OCR uploads.
- Authorized document inventory with file name, status, visibility, OCR indicator, extraction warning count, chunk count, updated time, and detail inspection with extraction/OCR timing.
- Chunk preview for the selected document, using the same RBAC checks as the query/retrieval path.
- Queued upload status for background ingestion jobs, with automatic polling until completion or failure.
- Retry action for failed background ingestion jobs.
- Admin operations summary for ingestion totals, job queue state, failed jobs, query cache hit rate, query latency, recent audit operations, and retrieval evaluation pass rate.

For the latest supported-format matrix, OCR notes, local-model switching instructions, validation checklist, and pending roadmap, see [Current Status And Roadmap](docs/current-status.md).

When running with Docker, the backend cannot read arbitrary Mac paths such as `/Users/name/Documents/file.pdf`. Put local files under `data/ingest/` in this repo, then enter the container path in the UI:

```text
/data/ingest/file.pdf
```

Docker Compose mounts `./data/ingest` into the backend container as `/data/ingest:ro`.

For convenience during local Docker development, Compose can also mount a host folder as read-only:

```text
HOST_DOWNLOADS_DIR -> /host-downloads
```

Set `HOST_DOWNLOADS_DIR` in `.env` to the folder you want Docker to expose. The default is `./data/host-downloads`. If you also want `file:///...` URLs from the host to be translated automatically, set `HOST_MOUNT_SOURCE_PREFIX` to the same host folder.

For DBeaver from the Mac, use the dedicated host port to avoid conflicts with any local PostgreSQL install:

```text
Host: 127.0.0.1
Port: 55432
Database: rag
Username: rag
Password: rag
```

The query endpoint uses the local model provider abstraction plus a vector index boundary. The default configuration keeps demos deterministic with hashing embeddings, the in-memory vector index, no reranker, and extractive answer generation. `VECTOR_INDEX_BACKEND=pgvector` enables the PostgreSQL/pgvector adapter when DB persistence is on, and `VECTOR_INDEX_BACKEND=qdrant` enables the Qdrant adapter for higher-scale vector experiments. `python -m app.rag.backfill_vectors` backfills persisted chunks into the selected vector backend. For local semantic embeddings or local answer generation, set the corresponding runtime to `ollama` with a running Ollama service. `RERANKER_PROVIDER=local` plus `LOCAL_RERANKER_RUNTIME=keyword` enables a deterministic local reranker; cross-encoder and vLLM rerankers remain reserved for later adapters.

Run the offline retrieval quality gate:

```bash
python -m app.eval.run
```

The current model strategy is local/open-source first. Defaults are:

```text
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_RUNTIME=hashing
LOCAL_EMBEDDING_MODEL_NAME=hashing-384
EMBEDDING_DIMENSIONS=384
LOCAL_EMBEDDING_BASE_URL=http://localhost:11434
LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS=30
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
LOCAL_LLM_BASE_URL=http://localhost:11434
PUBLIC_LLM_ENABLED=false
```

`app/rag/model_providers.py` defines the embedding and answer-generation interfaces. `LOCAL_EMBEDDING_RUNTIME=ollama` is available for local Ollama embeddings, and `LOCAL_LLM_RUNTIME=ollama` is available for local Ollama answer generation. Later phases can add vLLM-backed embeddings or generation. Public token-based LLM providers remain blocked unless `PUBLIC_LLM_ENABLED=true`. See [Model Providers](docs/model-providers.md) for the full configuration reference and adapter contract.

## Architecture

The editable architecture diagram is maintained in [docs/architecture.md](docs/architecture.md). Detailed auth, async ingestion, query, analytics, and RBAC flow diagrams are maintained in [docs/flow-diagrams.md](docs/flow-diagrams.md). Both render directly in GitHub and can be edited as Mermaid text.

## Week 1 Acceptance Criteria

- Database schema supports tenants, users, roles, documents, chunks, and audit logging.
- Every chunk stores access metadata: tenant, document, visibility, roles, source location, OCR flag.
- Chunking works for extracted plain text and preserves source metadata.
- OCR is represented as a first-class extraction path and can be enabled when dependencies are installed.
- Services can be started locally with Docker Compose.
- Unit tests validate chunk size, overlap, and metadata propagation.

## Notes

FastAPI is used instead of Flask because streaming, async background orchestration, and OpenAPI generation are useful for later RAG milestones. The scaffold still keeps orchestration simple enough to adapt to Flask if that decision is fixed.
