# Execution Runbook

## Health Checks

```bash
curl http://127.0.0.1:8000/health
docker compose ps
```

Expected health response:

```json
{"status":"ok","service":"rag-saas-docs-ingestion-poc"}
```

## Backend Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,parsing]"
python3 -m pytest
```

## Frontend Build

```bash
cd frontend
npm install
npm run build
```

## Frontend E2E Smoke Test

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

## Rebuild After Code Changes

Rebuild only the backend:

```bash
docker compose up -d --build backend
```

Rebuild the full stack:

```bash
docker compose up -d --build
```

## API Smoke Test

Upload a file:

```bash
curl -F tenant_id=00000000-0000-4000-8000-000000000001 \
  -F visibility=tenant \
  -F force_ocr=false \
  -F file=@./data/ingest/example.txt \
  http://127.0.0.1:8000/api/v1/documents/upload
```

Ask a question:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "00000000-0000-4000-8000-000000000001",
    "query": "What is knowledge representation?",
    "role_names": []
  }'
```

## Inspect Persisted Data

```bash
docker compose exec postgres psql -U rag -d rag
```

Useful queries:

```sql
select file_name, status, visibility, created_at
from documents
order by created_at desc
limit 10;

select d.file_name, count(c.id) as chunks
from documents d
left join document_chunks c on c.document_id = d.id
group by d.file_name, d.created_at
order by d.created_at desc
limit 10;

select action, resource_type, metadata, created_at
from audit_logs
order by created_at desc
limit 10;
```

## Troubleshooting

- If upload returns `413 Request Entity Too Large`, confirm the frontend nginx config includes `client_max_body_size 2g` and rebuild the frontend.
- If queries return no context, confirm the uploaded chunks are in `document_chunks` and the UI tenant ID is `00000000-0000-4000-8000-000000000001`.
- If DBeaver cannot connect, use port `55432`, not `5432`, when a local Postgres already uses `5432`.
- If Docker cannot read a host path, use browser upload or configure both `HOST_DOWNLOADS_DIR` and `HOST_MOUNT_SOURCE_PREFIX` in `.env`.
