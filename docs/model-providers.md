# Model Providers

The POC is local/open-source first. Query answering is wired through `app/rag/model_providers.py`, which owns two boundaries:

- `EmbeddingModel`: turns query and chunk text into vectors for retrieval ranking.
- `AnswerGenerator`: turns authorized retrieval results into the final answer text.

The default implementation is intentionally deterministic so local demos, tests, and the offline retrieval quality gate do not require model downloads or public API calls.

## Default Configuration

Use these defaults for local development and Docker Compose:

```text
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_RUNTIME=hashing
LOCAL_EMBEDDING_MODEL_NAME=hashing-384
EMBEDDING_DIMENSIONS=384
LOCAL_EMBEDDING_BASE_URL=http://localhost:11434
LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS=30
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

`LOCAL_EMBEDDING_BASE_URL` is used when `LOCAL_EMBEDDING_RUNTIME=ollama`; `LOCAL_LLM_BASE_URL` is used when `LOCAL_LLM_RUNTIME=ollama`. The default hashing and extractive runtimes do not call local model URLs.

## Supported Values Today

| Setting | Supported now | Reserved for later | Notes |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local` | public/provider-specific services | Non-local values fail fast today. |
| `LOCAL_EMBEDDING_RUNTIME` | `hashing`, `ollama` | `vllm` | `hashing` uses the deterministic in-process baseline; `ollama` calls `/api/embed` on `LOCAL_EMBEDDING_BASE_URL`. |
| `LOCAL_EMBEDDING_MODEL_NAME` | `hashing-384`, any installed Ollama embedding model | BGE, E5, Mixedbread, or adapter model names | Informational for hashing; sent as `model` for Ollama; included in metrics/cache keys. |
| `EMBEDDING_DIMENSIONS` | integer dimension count practical for local ranking | adapter-specific dimensions | Default is `384`; keep it greater than zero for hashing embeddings. |
| `VECTOR_INDEX_BACKEND` | `memory`, `pgvector`, `qdrant` | additional managed vector stores | `memory` keeps tests/local demos deterministic; `pgvector` stores embeddings in PostgreSQL; `qdrant` writes/searches the configured Qdrant collection. |
| `PGVECTOR_DIMENSIONS` | `1024` | adapter-specific dimensions | Matches the current `document_chunks.embedding vector(1024)` column. Shorter embeddings are padded for pgvector storage. |
| `VECTOR_BACKFILL_BATCH_SIZE` | positive integer | adapter-tuned values | Used by `python -m app.rag.backfill_vectors`. |
| `QDRANT_COLLECTION_NAME` | collection name | deployment-specific names | Default collection is `rag_chunks`. |
| `QDRANT_REQUEST_TIMEOUT_SECONDS` | positive number | deployment-specific values | Used by the Qdrant HTTP adapter. |
| `RERANKER_PROVIDER` | `none`, `local` | managed/provider-specific rerankers | `none` leaves hybrid retrieval order unchanged; `local` enables local runtimes. |
| `LOCAL_RERANKER_RUNTIME` | `none`, `keyword` | `cross-encoder`, `vllm` | `keyword` is deterministic and local; heavier runtimes remain reserved. |
| `LOCAL_RERANKER_MODEL_NAME` | `none`, `keyword-overlap` | local reranker model names | Included in cache keys/metrics when reranking is enabled. |
| `RERANKER_CANDIDATE_MULTIPLIER` | positive integer | adapter-tuned values | Controls how many initial candidates are retrieved before final top-k reranking. |
| `LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS` | positive number | adapter-specific timeouts | Used by Ollama HTTP clients. |
| `LLM_PROVIDER` | `local` | public token-based providers | Public providers require `PUBLIC_LLM_ENABLED=true` and adapter code. |
| `LOCAL_LLM_RUNTIME` | `extractive`, `ollama` | `vllm` | `extractive` selects sentences from authorized chunks; `ollama` calls `/api/generate` on `LOCAL_LLM_BASE_URL`. |
| `LOCAL_LLM_MODEL_NAME` | `extractive`, any installed Ollama generation model | local model names | Sent as `model` for Ollama; included in metrics/cache keys. |
| `PUBLIC_LLM_ENABLED` | `false` | `true` after policy approval and adapter implementation | Keeps external API usage opt-in. |

If `LOCAL_EMBEDDING_RUNTIME=vllm` or `LOCAL_LLM_RUNTIME=vllm` is set before those adapters exist, startup/query construction raises `ModelProviderConfigurationError`. That failure is deliberate: it prevents silently falling back to a different model path.

If `RERANKER_PROVIDER=local` is selected with `LOCAL_RERANKER_RUNTIME=cross-encoder` or `vllm` before those adapters exist, query construction raises `RerankerConfigurationError` for the same reason.

## Vector Indexing And Reranking

The query pipeline asks the configured vector index for tenant-safe candidates before hybrid scoring. Defaults use the in-memory vector index and deterministic hashing embeddings. When `VECTOR_INDEX_BACKEND=pgvector` and `ENABLE_DB_PERSISTENCE=true`, ingestion writes chunk embeddings to `document_chunks.embedding`, and query retrieval orders candidates with pgvector before the existing keyword/early-term/hybrid score is applied. `VECTOR_INDEX_BACKEND=qdrant` writes/searches vectors in Qdrant using RBAC metadata payload filters plus the application-level authorization check.

Backfill persisted chunks after changing vector backends or embedding models:

```bash
python -m app.rag.backfill_vectors
```

The reranker boundary runs after initial retrieval. The default `RERANKER_PROVIDER=none` returns the existing order unchanged while adding provider/runtime/model names to cache keys and metrics. `RERANKER_PROVIDER=local` with `LOCAL_RERANKER_RUNTIME=keyword` applies a deterministic local keyword-overlap rerank step. This keeps today stable and leaves a direct adapter point for local cross-encoder or vLLM reranking.

## Ollama Embeddings

To use Ollama embeddings with Ollama running on the same host as the backend:

1. Start Ollama on `http://localhost:11434`.
2. Pull an embedding model, for example `nomic-embed-text`.
3. Set:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text
LOCAL_EMBEDDING_BASE_URL=http://localhost:11434
```

When the backend runs inside Docker Compose and Ollama runs on the host machine, use:

```text
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
```

This host-Ollama path was smoke-tested with Docker backend/worker calling Mac Ollama, using `nomic-embed-text:latest`.

When Ollama runs as the optional Docker Compose service in this repo, use:

```text
LOCAL_EMBEDDING_BASE_URL=http://ollama:11434
```

The adapter calls `POST /api/embed` with the configured model and input text. Returned vectors are normalized before retrieval scoring so existing cosine ranking behavior remains consistent with the hashing baseline.

## Ollama Answer Generation

To use Ollama for answer generation with Ollama running on the same host as the backend:

1. Start Ollama on `http://localhost:11434`.
2. Pull a generation model, for example `llama3.1`.
3. Set:

```text
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1
LOCAL_LLM_BASE_URL=http://localhost:11434
```

When the backend runs inside Docker Compose and Ollama runs on the host machine, use:

```text
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

This host-Ollama path was smoke-tested with Docker backend/worker calling Mac Ollama, using `llama3.1:8b`.

When Ollama runs as the optional Docker Compose service in this repo, use:

```text
LOCAL_LLM_BASE_URL=http://ollama:11434
```

The adapter calls `POST /api/generate` with `stream=false`. The prompt instructs the model to answer only from authorized retrieved context and to say when there is not enough authorized evidence. Retrieval, RBAC filtering, citations, cache keys, and response metrics still happen in the application.

## Running Ollama In Docker Compose

The Compose file includes an optional `ollama` service under the `local-models` profile. It is not started by the default `docker compose up` command.

Start Ollama:

```bash
docker compose --profile local-models up -d ollama
```

Pull local models into the persistent `ollama_data` volume:

```bash
docker compose --profile local-models exec ollama ollama pull nomic-embed-text
docker compose --profile local-models exec ollama ollama pull llama3.1
```

Set the backend/worker model config in `.env`:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text
LOCAL_EMBEDDING_BASE_URL=http://ollama:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1
LOCAL_LLM_BASE_URL=http://ollama:11434
```

Then rebuild or restart the app services with the same profile:

```bash
docker compose --profile local-models up -d --build backend worker frontend
```

The model service can also be reached from the host at `http://localhost:11434`.

## Tested Host-Ollama Docker Settings

Use this `.env` block when Ollama runs on your Mac and backend/worker run in Docker Compose:

```text
LOCAL_EMBEDDING_RUNTIME=ollama
LOCAL_EMBEDDING_MODEL_NAME=nomic-embed-text:latest
LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:11434
LOCAL_LLM_RUNTIME=ollama
LOCAL_LLM_MODEL_NAME=llama3.1:8b
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
```

Restart and verify:

```bash
docker compose up -d --build backend worker
docker compose exec backend python -c "import os; print(os.environ['LOCAL_EMBEDDING_RUNTIME'], os.environ['LOCAL_LLM_RUNTIME'])"
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read().decode())"
```

Expected query metrics when both Ollama runtimes are active:

```json
{
  "local_llm_runtime": "ollama",
  "local_embedding_runtime": "ollama",
  "embedding_model": "nomic-embed-text:latest",
  "answer_model": "llama3.1:8b"
}
```

## Query And Cache Behavior

`RagPipeline` builds a `ModelProvider` at construction time. The provider supplies the embedding model to `HybridRetriever` and the answer generator used after retrieval.

Query responses include model metadata in `metrics`:

```json
{
  "llm_provider": "local",
  "local_llm_runtime": "extractive",
  "answer_model": "extractive",
  "embedding_provider": "local",
  "local_embedding_runtime": "hashing",
  "embedding_model": "hashing-384"
}
```

The Redis query cache key also includes provider, runtime, and model names. Changing model settings therefore creates a new cache entry instead of reusing an answer generated under a previous runtime.

## Runtime Status

Authenticated users can inspect the active model configuration through:

```text
GET /api/v1/model-status
```

The response reports the configured embedding and answer providers, runtimes, model names, readiness, and Ollama base URLs when an Ollama runtime is active. Hashing embeddings and extractive answer generation report ready without network calls. Ollama runtimes perform a lightweight `GET /api/tags` readiness check and mark the component not ready when Ollama is unreachable or the configured model has not been pulled.

The React console uses this endpoint to show the model readiness pill and the active embedding/answer runtime cards.

Ollama query-time failures raise `ModelProviderRequestError` with the operation, model name, endpoint, and HTTP status or timeout class. The query API converts those provider errors into `503 Service Unavailable` responses so callers see a clear local-model readiness issue instead of a generic server failure.

## Evaluation Behavior

`python -m app.eval.run` still uses the same extractive answer generator as the default local provider. This keeps the retrieval quality gate aligned with the production query path while avoiding network calls or model downloads.

## Adding A Future Local Adapter

When adding more local model support:

1. Implement an `EmbeddingModel`, an `AnswerGenerator`, or both in `app/rag/model_providers.py` or a focused submodule.
2. Use `LOCAL_EMBEDDING_BASE_URL` and `LOCAL_LLM_BASE_URL` for local service endpoints.
3. Keep `PUBLIC_LLM_ENABLED=false`; local adapters should not require public token-based APIs.
4. Add tests for config selection, adapter failure modes, status checks, cache-key separation, and query metrics.
5. Run `python3 -m pytest`, `python3 -m app.eval.run`, `npm run build`, and `docker compose config`.

Public token-based providers should be added only after deployment policy allows external API usage, and should remain gated behind `PUBLIC_LLM_ENABLED=true`.
