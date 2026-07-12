# RAG SaaS Docs Ingestion POC

Open-source proof of concept for a multi-tenant SaaS RAG document ingestion and query workflow. It handles browser file upload, PDF and Microsoft Office text extraction, OCR-ready parsing, chunking, RBAC-aware retrieval, Redis query caching, Postgres persistence, visible A&A/session management surfaces, and a React/Vite UI.

The milestone targets are:

- Week 1: database setup, document ingestion foundations, OCR-aware text extraction, and chunking strategies for a multi-tenant RAG SaaS that can scale toward approximately 1 TB of Microsoft Office, PDF, and image-backed documents.
- Week 2: RAG pipeline creation, Redis query caching, retrieval interface, citation output, and API contracts for the Week 3 UI.
- Week 3: React/Vite UI for document ingestion, role-aware querying, citations, cache status, and latency metrics.
- Week 4: Docker containerization plus unit, API E2E, and frontend E2E test coverage.
- Week 5: Keycloak OIDC login (Authorization Code + PKCE), JWT validation middleware, Postgres-backed RBAC, and stateless-JWT session management.

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

For full setup, execution, test, and GitHub export instructions, see:

- [Setup Guide](docs/setup.md)
- [Architecture Diagram](docs/architecture.md)
- [Execution Runbook](docs/runbook.md)
- [GitHub Export Guide](docs/github-export.md)
- [Week 6 Suggested Target Plan](docs/week6-plan.md)

## Scope Delivered

- FastAPI backend skeleton
- PostgreSQL schema with RBAC, tenants, documents, chunks, processing jobs, and audit logs
- pgvector-ready chunk table for embeddings
- Qdrant service included for higher-scale vector retrieval experiments
- Redis, MinIO, PostgreSQL, Qdrant, and Keycloak in Docker Compose
- OCR-aware parser abstraction
- Recursive token-aware chunking with metadata propagation
- Role-aware chunk metadata model
- Unit tests for chunking and metadata behavior
- Week 1 implementation plan and acceptance checklist
- Week 2 query pipeline with Redis-backed cache fallback
- RBAC-aware hybrid retrieval baseline
- Citation and latency metrics in query responses
- Week 3 React/Vite operational UI
- Week 4 backend/frontend Dockerfiles and Compose wiring
- API E2E and frontend Playwright smoke tests
- Visible A&A and session management panels for the POC workflow
- Keycloak OIDC login (Authorization Code + PKCE), JWT validation middleware, and stateless-JWT session management with silent refresh
- Server-side RBAC resolved from Postgres (`app_users`/`roles`/`user_roles`), with tenant_id/roles always taken from the validated token -- never from request bodies
- PDF, Word DOCX, Excel XLSX, PowerPoint PPTX, text, CSV/TSV, markdown, and image intake
- Document management inventory with authorized list/detail APIs, ingestion status, visibility, OCR flags, chunk counts, and chunk preview

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
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `POST /api/v1/query`

The document list/detail endpoints power the UI's Document Management panel. They apply the same tenant and RBAC rules as retrieval: users can inspect only documents and chunks their authenticated identity is authorized to see.

The ingestion endpoint accepts a local file path for Week 1 development. Production upload should stream files into MinIO first, then enqueue parsing and chunking workers.

The upload endpoint accepts multipart browser uploads and is the preferred local SaaS-style flow because it does not require Docker path mapping.

Supported POC intake formats:

- PDF
- Word DOCX
- Excel XLSX
- PowerPoint PPTX
- TXT, Markdown, CSV, TSV
- PNG, JPG/JPEG, TIFF, BMP through OCR

Legacy binary Office formats such as DOC, XLS, and PPT should be converted to DOCX, XLSX, or PPTX before ingestion.

The Dockerized frontend nginx proxy allows uploads up to `2g` via `client_max_body_size`. Production deployments should use direct-to-object-storage multipart/resumable uploads for very large files.

## Document Management UI

After login, the frontend shows:

- A&A and session management panels so the resolved tenant, roles, token expiry, and refresh behavior are visible.
- Format intake guidance for PDF, DOCX, XLSX, PPTX, text/CSV/markdown, and image OCR uploads.
- Authorized document inventory with file name, status, visibility, OCR indicator, chunk count, updated time, and detail inspection.
- Chunk preview for the selected document, using the same RBAC checks as the query/retrieval path.

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

The query endpoint uses an in-process development store and deterministic local embeddings. Production should persist chunks/embeddings in PostgreSQL/Qdrant and serve open source embedding/LLM models through workers or vLLM.

## Architecture

The editable architecture diagram is maintained in [docs/architecture.md](docs/architecture.md). It renders directly in GitHub and can be edited as Mermaid text.

## Week 1 Acceptance Criteria

- Database schema supports tenants, users, roles, documents, chunks, and audit logging.
- Every chunk stores access metadata: tenant, document, visibility, roles, source location, OCR flag.
- Chunking works for extracted plain text and preserves source metadata.
- OCR is represented as a first-class extraction path and can be enabled when dependencies are installed.
- Services can be started locally with Docker Compose.
- Unit tests validate chunk size, overlap, and metadata propagation.

## Notes

FastAPI is used instead of Flask because streaming, async background orchestration, and OpenAPI generation are useful for later RAG milestones. The scaffold still keeps orchestration simple enough to adapt to Flask if that decision is fixed.
