# Setup Guide

This guide prepares the RAG SaaS document ingestion POC for local execution.

## Prerequisites

- Docker Desktop
- Git
- Python 3.11+ for local backend tests
- Node.js 22+ for local frontend build and Playwright tests

## Clone And Configure

```bash
git clone <your-github-repo-url>
cd rag-saas-docs-ingestion-poc
cp .env.example .env
```

Optional: edit `.env` if you want Docker to expose a local document folder:

```text
HOST_DOWNLOADS_DIR=/Users/your-name/Downloads
HOST_MOUNT_SOURCE_PREFIX=/Users/your-name/Downloads
```

Docker mounts that host folder into the backend as:

```text
/host-downloads
```

With both values set, a path such as `file:///Users/your-name/Downloads/book.pdf` is mapped to `/host-downloads/book.pdf` inside the backend container.

The default model settings are local and deterministic:

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

No model download or public LLM token is required for the default stack. See [Model Providers](model-providers.md) before changing these values. `LOCAL_EMBEDDING_RUNTIME=ollama` and `LOCAL_LLM_RUNTIME=ollama` are supported when Ollama is running locally; vLLM embeddings and generation are reserved until their adapters are implemented.

## Start Full Stack

```bash
docker compose up -d --build
```

Services:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- Worker: `python -m app.worker` inside Docker Compose, polling Redis for queued ingestion jobs
- Postgres: `127.0.0.1:55432`
- Redis: `127.0.0.1:6379`
- MinIO: `http://127.0.0.1:9001`
- Qdrant: `http://127.0.0.1:6333`
- Keycloak: `http://127.0.0.1:8080`
- Optional Ollama service: `http://127.0.0.1:11434` when started with `docker compose --profile local-models up -d ollama`

## Optional Local Models In Docker

The default stack does not start Ollama. To run Ollama inside Docker Compose:

```bash
docker compose --profile local-models up -d ollama
docker compose --profile local-models exec ollama ollama pull nomic-embed-text
docker compose --profile local-models exec ollama ollama pull llama3.1
```

Then set these values in `.env` if you want the backend and worker containers to use the Compose Ollama service:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text
LOCAL_EMBEDDING_BASE_URL=http://ollama:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1
LOCAL_LLM_BASE_URL=http://ollama:11434
```

Restart app services with the profile:

```bash
docker compose --profile local-models up -d --build backend worker frontend
```

## Default Database Login

Use these settings in DBeaver:

```text
Host: 127.0.0.1
Port: 55432
Database: rag
Username: rag
Password: rag
```

## Default Tenant

The database seed creates a demo tenant used by the UI:

```text
00000000-0000-4000-8000-000000000001
```

## Signing In (Keycloak)

The Keycloak container auto-imports `infra/keycloak/realm-export.json` on first
start, which creates the `rag` realm, the `rag-frontend` (public, PKCE) and
`rag-api` (bearer-only) clients, and five demo users -- one per role, all in
the demo tenant above, all with password `Passw0rd!`:

| Username         | Role        |
| ----------------- | ----------- |
| `admin-demo`       | admin       |
| `finance-demo`     | finance     |
| `engineer-demo`    | engineering |
| `legal-demo`       | legal       |
| `support-demo`     | support     |

Open `http://127.0.0.1:5173`, click **Sign in with Keycloak**, and log in as
one of the users above. The backend resolves your tenant and roles from
Postgres (`app_users` / `roles` / `user_roles`, seeded from the same realm
export); there is no manual tenant ID or role picker in the UI anymore.

To manage users/roles directly, use the Keycloak admin console at
`http://127.0.0.1:8080` (`admin` / `admin`), realm `rag`.

## Upload Documents

Preferred local workflow:

1. Open `http://127.0.0.1:5173`.
2. Use the browser upload control.
3. Keep visibility as `tenant` unless testing role-restricted chunks.
4. Ask a question in the query panel.

For larger documents or a more production-like workflow, use **Upload to queue**. The backend returns a processing job immediately, the `worker` service picks it up from Redis, and the UI polls until the job reaches `completed` or `failed`.

Supported POC intake formats:

- PDF
- Word DOCX
- Excel XLSX
- PowerPoint PPTX
- TXT, Markdown, CSV, TSV
- PNG, JPG/JPEG, TIFF, BMP through OCR

Legacy DOC, XLS, and PPT files should be converted to DOCX, XLSX, or PPTX.

Alternative mounted-path workflow:

1. Put files in `data/ingest`.
2. In the UI, use a local path like:

```text
/data/ingest/example.pdf
```

## Verify Background Worker

```bash
docker compose ps backend worker frontend postgres redis
docker compose logs --tail=50 worker
```

Expected result:

- `backend` is healthy.
- `worker` is up and logs `Starting RAG document processing worker`.
- Queued uploads appear in the UI as job cards, then transition to `completed` after the worker processes them.

## Stop Stack

```bash
docker compose down
```

To remove local Docker volumes and reset all data:

```bash
docker compose down -v
```
