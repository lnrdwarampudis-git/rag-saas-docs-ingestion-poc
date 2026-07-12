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

## Model Provider Config Check

The default stack uses deterministic local providers, so this should work without model downloads or public API tokens:

```bash
python3 -m app.eval.run
```

Expected result:

```text
Cases: 3 passed=3 failed=0
```

Confirm Docker Compose has the same model settings:

```bash
docker compose config
```

The `backend` and `worker` environments should include:

```text
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_RUNTIME=hashing
LOCAL_EMBEDDING_MODEL_NAME=hashing-384
EMBEDDING_DIMENSIONS=384
LOCAL_EMBEDDING_BASE_URL=http://localhost:11434
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
LOCAL_LLM_BASE_URL=http://localhost:11434
PUBLIC_LLM_ENABLED=false
```

See [Model Providers](model-providers.md) for the full setting list, cache behavior, and adapter contract.

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

Every `/api/v1/*` route now requires a valid Keycloak access token; `tenant_id`
and roles are resolved from that token, not from the request body.

Get a token for a demo user (direct/password grant, enabled on `rag-frontend`
for exactly this kind of scripted smoke test):

```bash
TOKEN=$(curl -s -X POST \
  http://127.0.0.1:8080/realms/rag/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=rag-frontend \
  -d username=admin-demo \
  -d password='Passw0rd!' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Upload a file:

```bash
UPLOAD_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  -F visibility=tenant \
  -F force_ocr=false \
  -F file=@./data/ingest/example.txt \
  http://127.0.0.1:8000/api/v1/documents/upload)

echo "$UPLOAD_RESPONSE"
DOC_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")
```

Inspect the authorized document inventory:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/documents

curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/documents/$DOC_ID
```

Queue a file for background processing:

```bash
JOB_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  -F visibility=tenant \
  -F force_ocr=false \
  -F file=@./data/ingest/example.txt \
  http://127.0.0.1:8000/api/v1/documents/upload-async)

echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/processing-jobs/$JOB_ID
```

In Docker, the `worker` service polls Redis and processes queued jobs automatically. For a local API-only smoke test without the worker loop, run one job explicitly:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/processing-jobs/$JOB_ID/run
```

Ask a question:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{
    "query": "What is knowledge representation?"
  }'
```

Check who a token resolves to (tenant + roles), useful when debugging RBAC:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/auth/me
```

## UI Smoke Test

1. Open `http://127.0.0.1:5173`.
2. Sign in with `admin-demo` / `Passw0rd!`.
3. Confirm the A&A panel shows the resolved tenant and roles, and the Session panel shows token expiry/refresh state.
4. Upload a PDF, DOCX, XLSX, PPTX, text/CSV/markdown, or image file from the Upload panel.
5. Use "Upload to queue" to exercise the background processing path; the UI polls job status until the worker completes or fails it.
6. Use Document Management to refresh the authorized inventory, open the uploaded document, and confirm chunk previews are visible.
7. Ask a question in the Query panel and confirm citations/latency/cache status appear.

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
- If any `/api/v1/*` call returns `401 Unauthorized`, your token is missing, expired, or was issued before `docker compose down -v` reseeded a new realm/tenant -- sign out and back in (or re-fetch a token per the smoke test above).
- If queries return no context, confirm the uploaded chunks are in `document_chunks` and that you're signed in as a user in the same tenant that uploaded them (the default demo tenant is `00000000-0000-4000-8000-000000000001`).
- If query construction fails with `ModelProviderConfigurationError`, check `.env` for unsupported provider values. Today the implemented runtimes are `EMBEDDING_PROVIDER=local`, `LOCAL_EMBEDDING_RUNTIME=hashing`, `LLM_PROVIDER=local`, and `LOCAL_LLM_RUNTIME=extractive`; Ollama/vLLM names are reserved until adapters are added.
- If Keycloak login loops back to the sign-in page or 500s on `/protocol/openid-connect/certs`, rebuild the backend (`docker compose up -d --build backend`) -- an older backend build may not skip Keycloak's non-signing (`use=enc`) JWKS key correctly.
- If demo users/roles are missing after applying changes, you likely reused an old Postgres/Keycloak volume: run `docker compose down -v` (note the `-v`) before `docker compose up -d --build` so `init.sql` and the realm import both re-run.
- If DBeaver cannot connect, use port `55432`, not `5432`, when a local Postgres already uses `5432`.
- If Docker cannot read a host path, use browser upload or configure both `HOST_DOWNLOADS_DIR` and `HOST_MOUNT_SOURCE_PREFIX` in `.env`.
