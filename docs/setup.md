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

## Start Full Stack

```bash
docker compose up -d --build
```

Services:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- Postgres: `127.0.0.1:55432`
- Redis: `127.0.0.1:6379`
- MinIO: `http://127.0.0.1:9001`
- Qdrant: `http://127.0.0.1:6333`
- Keycloak: `http://127.0.0.1:8080`

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

## Upload Documents

Preferred local workflow:

1. Open `http://127.0.0.1:5173`.
2. Use the browser upload control.
3. Keep visibility as `tenant` unless testing role-restricted chunks.
4. Ask a question in the query panel.

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

## Stop Stack

```bash
docker compose down
```

To remove local Docker volumes and reset all data:

```bash
docker compose down -v
```
