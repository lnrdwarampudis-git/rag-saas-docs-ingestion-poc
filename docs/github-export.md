# GitHub Export Guide

Use this checklist to publish the POC to a GitHub repository.

## 1. Review Local Files

Do not commit local runtime data:

- `.env`
- `data/`
- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- Playwright reports and test results

These are already covered by `.gitignore`.

## 2. Initialize Git

```bash
git init
git add .
git status
git commit -m "Initial RAG SaaS document ingestion POC"
```

## 3. Connect GitHub Remote

Create an empty GitHub repository, then connect it:

```bash
git branch -M main
git remote add origin https://github.com/<your-user-or-org>/<your-repo>.git
git push -u origin main
```

If the remote already exists:

```bash
git remote set-url origin https://github.com/<your-user-or-org>/<your-repo>.git
git push -u origin main
```

## 4. Recommended Repository Description

```text
Open-source SaaS RAG document ingestion POC with FastAPI, React/Vite, PostgreSQL, Redis, Qdrant, MinIO, Keycloak, OCR-ready parsing, RBAC metadata, and Docker Compose.
```

## 5. Suggested GitHub Topics

```text
rag, fastapi, react, vite, postgres, pgvector, redis, qdrant, minio, keycloak, ocr, document-ingestion, open-source
```

## 6. Verify After Clone

On another machine or clean folder:

```bash
git clone https://github.com/<your-user-or-org>/<your-repo>.git
cd <your-repo>
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:8000/health
```
