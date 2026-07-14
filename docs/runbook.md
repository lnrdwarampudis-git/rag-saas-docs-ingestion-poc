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

The authenticated model runtime check is:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/model-status
```

With default local providers, expect ready hashing embeddings and ready extractive answer generation:

```json
{
  "llm_provider": "local",
  "embedding_provider": "local",
  "embedding": {
    "provider": "local",
    "runtime": "hashing",
    "model_name": "hashing-384",
    "ready": true
  },
  "answer": {
    "provider": "local",
    "runtime": "extractive",
    "model_name": "extractive",
    "ready": true
  }
}
```

The authenticated admin analytics check is:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/analytics
```

When Postgres persistence is enabled, query volume, cache hits, and latency come
from persisted `query_events`; local non-persistent tests fall back to the
in-memory query event buffer. The same response includes p95 latency, recent
average latency, recent tenant audit events from `audit_logs`, and evaluation
groundedness so the UI can show an operations history and live quality signals.

Expected response sections:

```json
{
  "documents": {},
  "jobs": {},
  "queries": {},
  "retrieval": {},
  "evaluation": {}
}
```

For production deployment checks, CI gates, and backup/restore commands, see [Deployment Hardening](deployment-hardening.md).

## Backend Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,parsing]"
python3 -m pytest
```

If your local `.env` points Docker containers at Mac-host Ollama with
`host.docker.internal`, run host-side tests with deterministic provider
overrides so pytest does not try to resolve Docker-only hostnames:

```bash
env LOCAL_EMBEDDING_RUNTIME=hashing \
  LOCAL_EMBEDDING_MODEL_NAME=hashing-384 \
  LOCAL_LLM_RUNTIME=extractive \
  LOCAL_LLM_MODEL_NAME=extractive \
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
LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS=30
LOCAL_MODEL_PROFILE=custom
LOCAL_MODEL_GPU_PROFILE=none
VECTOR_INDEX_BACKEND=memory
PGVECTOR_DIMENSIONS=1024
VECTOR_BACKFILL_BATCH_SIZE=100
QDRANT_COLLECTION_NAME=rag_chunks
QDRANT_REQUEST_TIMEOUT_SECONDS=10
RERANKER_PROVIDER=none
LOCAL_RERANKER_RUNTIME=none
LOCAL_RERANKER_MODEL_NAME=none
RERANKER_CANDIDATE_MULTIPLIER=4
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
LOCAL_LLM_BASE_URL=http://localhost:11434
PUBLIC_LLM_ENABLED=false
```

See [Model Providers](model-providers.md) for the full setting list, cache behavior, and adapter contract.

Confirm large-file and retrieval settings inside the backend container:

```bash
docker compose exec backend python -c "import os; keys=['UPLOAD_SESSION_PART_BYTES','UPLOAD_SESSION_MAX_PARTS','UPLOAD_SESSION_STORAGE_BACKEND','UPLOAD_SESSION_CLEANUP_MAX_AGE_HOURS','UPLOAD_SESSION_LIFECYCLE_EXPIRATION_DAYS','WORKER_MAX_JOBS_PER_RUN','PROCESSING_JOB_MAX_ATTEMPTS','PROCESSING_DEAD_LETTER_QUEUE_NAME','LOCAL_MODEL_PROFILE','LOCAL_MODEL_GPU_PROFILE','VECTOR_INDEX_BACKEND','PGVECTOR_DIMENSIONS','QDRANT_COLLECTION_NAME','RERANKER_PROVIDER','LOCAL_RERANKER_RUNTIME','LOCAL_RERANKER_BASE_URL','RETRIEVAL_LATENCY_WARNING_MS','TOTAL_LATENCY_WARNING_MS']; print({k: os.environ.get(k) for k in keys})"
```

Use `VECTOR_INDEX_BACKEND=pgvector` only with `ENABLE_DB_PERSISTENCE=true`. Use `VECTOR_INDEX_BACKEND=qdrant` for the Qdrant adapter, then run `python -m app.rag.vector_ops` after changing vector backend or embedding model. The default `RERANKER_PROVIDER=none` can be changed to `RERANKER_PROVIDER=local` and `LOCAL_RERANKER_RUNTIME=keyword` for deterministic local reranking, or `cross-encoder` / `vllm` for a local HTTP reranker. Check `/api/v1/model-status` or the UI model panel after changes; it reports vector-index readiness, reranker readiness, and the configured latency warning thresholds.

Run the vector ops check/backfill command after changing vector backend or embedding model:

```bash
docker compose exec backend python -m app.rag.vector_ops
```

Clean up abandoned upload sessions and temporary parts:

```bash
docker compose exec backend python -m app.rag.cleanup_upload_sessions --max-age-hours 24
```

Apply MinIO lifecycle expiration for abandoned upload-session objects:

```bash
docker compose exec backend python -m app.rag.minio_lifecycle
```

For browser-driven large files, sign in to the UI, choose a file, and use `Upload session`. With `UPLOAD_SESSION_STORAGE_BACKEND=filesystem`, parts stream through the backend. With `UPLOAD_SESSION_STORAGE_BACKEND=minio`, the UI requests a presigned URL per part, uploads directly to MinIO, marks the part complete, and then completes the session into the async queue. In Docker, use `MINIO_ENDPOINT=http://minio:9000` for service-to-service calls and `MINIO_PUBLIC_ENDPOINT=http://localhost:9000` for browser-reachable presigned URLs.

Configure local MinIO CORS before using browser direct upload mode:

```bash
docker run --rm --network rag-saas-docs-ingestion-poc_default \
  -v "$PWD/infra/minio/upload-session-cors.json:/cors.json:ro" \
  minio/mc sh -c "mc alias set local http://minio:9000 minio minio123 && mc mb -p local/rag-upload-sessions && mc cors set local/rag-upload-sessions /cors.json"
```

## OCR Runtime Check

The backend image includes Tesseract for image OCR and scanned-PDF OCR. Confirm it is available:

```bash
docker compose exec backend tesseract --version
```

Confirm OCR settings inside the backend container:

```bash
docker compose exec backend python -c "import os; keys=['OCR_LANGUAGE','OCR_PDF_DPI','OCR_MAX_PDF_PAGES']; print({k: os.environ.get(k) for k in keys})"
```

Expected defaults:

```text
OCR_LANGUAGE=eng
OCR_PDF_DPI=200
OCR_MAX_PDF_PAGES=20
```

Confirm installed Tesseract language packs:

```bash
docker compose exec backend tesseract --list-langs
```

The default backend image installs English (`eng`) through `tesseract-ocr-eng`. To add another language, add the matching Debian package to `Dockerfile.backend`, rebuild backend/worker images, and set `OCR_LANGUAGE` to the matching Tesseract code. Examples:

```text
tesseract-ocr-spa -> OCR_LANGUAGE=spa
tesseract-ocr-fra -> OCR_LANGUAGE=fra
tesseract-ocr-deu -> OCR_LANGUAGE=deu
```

Tesseract also accepts combined language codes when every pack is installed, for example `OCR_LANGUAGE=eng+spa`.

Scanned PDFs are rendered page-by-page with PyMuPDF before Tesseract OCR. Increase `OCR_MAX_PDF_PAGES` for longer scanned documents, and tune `OCR_PDF_DPI` when OCR quality or memory usage needs adjustment.

## Ollama Container Check

Start the optional Ollama service:

```bash
docker compose --profile local-models up -d ollama
docker compose --profile local-models exec ollama ollama list
```

Pull common local models:

```bash
docker compose --profile local-models exec ollama ollama pull nomic-embed-text
docker compose --profile local-models exec ollama ollama pull llama3.1
```

When backend and worker run in Compose and should use this service, set:

```text
LOCAL_EMBEDDING_BASE_URL=http://ollama:11434
LOCAL_LLM_BASE_URL=http://ollama:11434
```

Then restart:

```bash
docker compose --profile local-models up -d --build backend worker
```

## Mac-Host Ollama Container Check

Use this path when Ollama runs directly on the Mac and backend/worker run in Docker.

Confirm the backend container can see the Mac Ollama service:

```bash
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read().decode())"
```

Set `.env`:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text:latest
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1:8b
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

Restart backend and worker:

```bash
docker compose up -d --build backend worker
```

Confirm the live backend environment:

```bash
docker compose exec backend python -c "import os; keys=['LOCAL_EMBEDDING_RUNTIME','LOCAL_EMBEDDING_MODEL_NAME','LOCAL_EMBEDDING_BASE_URL','LOCAL_LLM_RUNTIME','LOCAL_LLM_MODEL_NAME','LOCAL_LLM_BASE_URL']; print({k: os.environ.get(k) for k in keys})"
```

Expected values:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text:latest
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1:8b
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

After signing in through the UI, the topbar model pill should show `Models ready`. The query metrics row should show `ollama / nomic-embed-text:latest` for embeddings and `ollama / llama3.1:8b` for answer generation.

Run a small authenticated API smoke from inside the backend container:

```bash
docker compose exec backend python - <<'PY'
import json
from pathlib import Path
import urllib.parse
import urllib.request

Path('/data/uploads/rag-ollama-smoke.txt').write_text(
    'Ollama local models provide private embeddings and local answer generation.\n',
    encoding='utf-8',
)

def request(url, data=None, headers=None, timeout=180):
    payload = None
    if isinstance(data, dict):
        payload = json.dumps(data).encode('utf-8')
        headers = {'content-type': 'application/json', **(headers or {})}
    req = urllib.request.Request(url, data=payload, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))

token_data = urllib.parse.urlencode({
    'grant_type': 'password',
    'client_id': 'rag-frontend',
    'username': 'admin-demo',
    'password': 'Passw0rd!',
}).encode('utf-8')
token_req = urllib.request.Request(
    'http://keycloak:8080/realms/rag/protocol/openid-connect/token',
    data=token_data,
    headers={'content-type': 'application/x-www-form-urlencoded', 'Host': 'localhost:8080'},
)
with urllib.request.urlopen(token_req, timeout=30) as response:
    token = json.loads(response.read().decode('utf-8'))['access_token']

headers = {'Authorization': f'Bearer {token}'}
request(
    'http://127.0.0.1:8000/api/v1/documents/ingest',
    {'local_path': '/data/uploads/rag-ollama-smoke.txt', 'visibility': 'tenant', 'allowed_role_names': [], 'force_ocr': False},
    headers=headers,
)
query = request(
    'http://127.0.0.1:8000/api/v1/query',
    {'query': 'What provides private embeddings and local answer generation?', 'top_k': 3},
    headers=headers,
)
print(json.dumps(query['metrics'], indent=2))
print(query['answer'])
PY
```

Expected metrics include:

```json
{
  "local_llm_runtime": "ollama",
  "local_embedding_runtime": "ollama",
  "embedding_model": "nomic-embed-text:latest",
  "answer_model": "llama3.1:8b"
}
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

In Docker, the `worker` service polls `rag:processing-jobs` and `worker-ocr` polls `rag:processing-jobs:ocr`. Forced OCR uploads route to the OCR queue automatically. Confirm queue configuration:

```bash
docker compose exec backend python -c "import os; keys=['PROCESSING_QUEUE_NAME','OCR_PROCESSING_QUEUE_NAME']; print({k: os.environ.get(k) for k in keys})"
docker compose logs --tail=50 worker
docker compose logs --tail=50 worker-ocr
```

For a local API-only smoke test without the worker loop, run one job explicitly:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/processing-jobs/$JOB_ID/run
```

Retry a failed background job:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/processing-jobs/$JOB_ID/retry
```

Cancel a queued or processing background job:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/processing-jobs/$JOB_ID/cancel
```

Inspect the Redis dead-letter queue for jobs that failed after the configured max attempts:

```bash
docker compose exec redis redis-cli LRANGE rag:processing-jobs:dead-letter 0 -1
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

Check the tenant-scoped analytics summary:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/analytics
```

Filter recent audit operations:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/analytics?action=processing_job.cancelled&resource_type=processing_job"
```

## UI Smoke Test

1. Open `http://127.0.0.1:5173`.
2. Sign in with `admin-demo` / `Passw0rd!`.
3. Confirm the A&A panel shows the resolved tenant and roles, and the Session panel shows token expiry/refresh state.
4. Upload a PDF, DOCX, XLSX, PPTX, text/CSV/markdown, or image file from the Upload panel.
5. Use "Upload to queue" to exercise the background processing path; the UI polls job status until the worker completes, fails, or is cancelled. Use the cancel action for queued/processing jobs and the retry action for failed jobs.
6. Use Document Management to refresh the authorized inventory, open the uploaded document, and confirm chunk previews are visible.
7. Ask a question in the Query panel and confirm citations plus run details appear: cache outcome, contexts used, top score, retrieval/total latency, embedding runtime, answer runtime, and retrieval thresholds.
8. Confirm the Evaluation panel shows the retrieval quality gate with all cases passing and context precision, context recall, and answer relevance averages.
9. Confirm the Analytics panel shows document totals, job queue/failure state, query cache hit rate, average latency, recent operations, and evaluation pass rate.

If the query API returns `503 Service Unavailable`, read the `detail` field. Ollama provider errors include the failed operation, configured model, endpoint, and whether the failure was a timeout, HTTP status, invalid JSON response, or transport error.

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

select action, metadata->>'query_sha256' as query_hash, metadata->>'cached' as cached, created_at
from audit_logs
where action = 'query.executed'
order by created_at desc
limit 10;

select cached, retrieval_ms, total_ms, created_at
from query_events
order by created_at desc
limit 10;

select event, status, attempts, metadata, created_at
from processing_job_events
order by created_at desc
limit 20;

select embedding_model, answer_model, vector_index_backend, reranker_runtime,
       avg(total_ms) as avg_total_ms, max(total_ms) as max_total_ms, count(*) as samples
from model_latency_events
group by embedding_model, answer_model, vector_index_backend, reranker_runtime
order by samples desc;

select cases, failed, context_precision, answer_groundedness, created_at
from evaluation_runs
order by created_at desc
limit 10;
```

## Troubleshooting

- If upload returns `413 Request Entity Too Large`, confirm the frontend nginx config includes `client_max_body_size 2g` and rebuild the frontend.
- If any `/api/v1/*` call returns `401 Unauthorized`, your token is missing, expired, or was issued before `docker compose down -v` reseeded a new realm/tenant -- sign out and back in (or re-fetch a token per the smoke test above).
- If queries return no context, confirm the uploaded chunks are in `document_chunks` and that you're signed in as a user in the same tenant that uploaded them (the default demo tenant is `00000000-0000-4000-8000-000000000001`).
- If query construction fails with `ModelProviderConfigurationError`, check `.env` for unsupported provider values. Today the implemented runtimes are `EMBEDDING_PROVIDER=local`, `LOCAL_EMBEDDING_RUNTIME=hashing`, `ollama`, or `vllm`, `LLM_PROVIDER=local`, and `LOCAL_LLM_RUNTIME=extractive`, `ollama`, or `vllm`.
- If you only want to switch local model modes, prefer `LOCAL_MODEL_PROFILE=local-default`, `host-ollama`, `compose-ollama`, or `vllm-gpu`; use `LOCAL_MODEL_PROFILE=custom` when setting individual runtime values manually.
- If `LOCAL_EMBEDDING_RUNTIME=ollama` fails with `ModelProviderRequestError`, confirm Ollama is running, `LOCAL_EMBEDDING_BASE_URL` is reachable from the backend process, and `LOCAL_EMBEDDING_MODEL_NAME` has been pulled locally. For Docker Compose with Ollama on the host machine, use `LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434`.
- If `LOCAL_LLM_RUNTIME=ollama` fails with `ModelProviderRequestError`, confirm Ollama is running, `LOCAL_LLM_BASE_URL` is reachable from the backend process, and `LOCAL_LLM_MODEL_NAME` has been pulled locally. For Docker Compose with Ollama on the host machine, use `LOCAL_LLM_BASE_URL=http://host.docker.internal:11434`.
- If `/api/v1/model-status` says Ollama is reachable but a configured model is missing, run `ollama list` on the Mac or `docker compose --profile local-models exec ollama ollama list` for the Compose service. Pull the exact model name shown in `.env`; examples are `nomic-embed-text:latest` and `llama3.1:8b`.
- If `/api/v1/model-status` says `/api/tags` did not return valid JSON, confirm the base URL points to Ollama itself and not a proxy, browser error page, or unrelated local service.
- If a query returns `503` with a timeout detail, either increase `LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS`, use a smaller model, or warm the model with a direct Ollama request before the demo.
- If Ollama runs as the Compose service, use `http://ollama:11434` as the base URL from backend/worker containers, and include `--profile local-models` when starting services.
- If Keycloak login loops back to the sign-in page or 500s on `/protocol/openid-connect/certs`, rebuild the backend (`docker compose up -d --build backend`) -- an older backend build may not skip Keycloak's non-signing (`use=enc`) JWKS key correctly.
- If demo users/roles are missing after applying changes, you likely reused an old Postgres/Keycloak volume: run `docker compose down -v` (note the `-v`) before `docker compose up -d --build` so `init.sql` and the realm import both re-run.
- If DBeaver cannot connect, use port `55432`, not `5432`, when a local Postgres already uses `5432`.
- If Docker cannot read a host path, use browser upload or configure both `HOST_DOWNLOADS_DIR` and `HOST_MOUNT_SOURCE_PREFIX` in `.env`.
