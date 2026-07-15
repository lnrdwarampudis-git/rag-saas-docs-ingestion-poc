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
LOCAL_RERANKER_BASE_URL=http://localhost:8081
LOCAL_RERANKER_REQUEST_TIMEOUT_SECONDS=30
RERANKER_CANDIDATE_MULTIPLIER=4
RETRIEVAL_LATENCY_WARNING_MS=1500
TOTAL_LATENCY_WARNING_MS=5000
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
LOCAL_LLM_BASE_URL=http://localhost:11434
PUBLIC_LLM_ENABLED=false
PUBLIC_LLM_BASE_URL=https://api.openai.com
PUBLIC_LLM_API_KEY=
PUBLIC_LLM_MODEL_NAME=
PUBLIC_EMBEDDING_MODEL_NAME=
```

`LOCAL_EMBEDDING_BASE_URL` is used when `LOCAL_EMBEDDING_RUNTIME=ollama`; `LOCAL_LLM_BASE_URL` is used when `LOCAL_LLM_RUNTIME=ollama`. The default hashing and extractive runtimes do not call local model URLs.

## Supported Values Today

| Setting | Supported now | Reserved for later | Notes |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local`, `openai` | additional provider-specific services | `openai` uses the public OpenAI-compatible embeddings adapter and requires `PUBLIC_LLM_ENABLED=true`. |
| `LOCAL_EMBEDDING_RUNTIME` | `hashing`, `ollama`, `vllm` | adapter-specific runtimes | `hashing` uses the deterministic in-process baseline; `ollama` calls `/api/embed`; `vllm` calls OpenAI-compatible `/v1/embeddings`. |
| `LOCAL_EMBEDDING_MODEL_NAME` | `hashing-384`, any installed Ollama embedding model | BGE, E5, Mixedbread, or adapter model names | Informational for hashing; sent as `model` for Ollama; included in metrics/cache keys. |
| `EMBEDDING_DIMENSIONS` | integer dimension count practical for local ranking | adapter-specific dimensions | Default is `384`; keep it greater than zero for hashing embeddings. |
| `VECTOR_INDEX_BACKEND` | `memory`, `pgvector`, `qdrant` | additional managed vector stores | `memory` keeps tests/local demos deterministic; `pgvector` stores embeddings in PostgreSQL; `qdrant` writes/searches the configured Qdrant collection. |
| `PGVECTOR_DIMENSIONS` | `1024` | adapter-specific dimensions | Matches the current `document_chunks.embedding vector(1024)` column. Shorter embeddings are padded for pgvector storage. |
| `VECTOR_BACKFILL_BATCH_SIZE` | positive integer | adapter-tuned values | Used by `python -m app.rag.vector_ops` and `python -m app.rag.backfill_vectors`. |
| `QDRANT_COLLECTION_NAME` | collection name | deployment-specific names | Default collection is `rag_chunks`. |
| `QDRANT_REQUEST_TIMEOUT_SECONDS` | positive number | deployment-specific values | Used by the Qdrant HTTP adapter. |
| `RERANKER_PROVIDER` | `none`, `local` | managed/provider-specific rerankers | `none` leaves hybrid retrieval order unchanged; `local` enables local runtimes. |
| `LOCAL_RERANKER_RUNTIME` | `none`, `keyword`, `cross-encoder`, `vllm` | adapter-specific runtimes | `keyword` is deterministic; `cross-encoder` and `vllm` call a local HTTP `/rerank` endpoint. |
| `LOCAL_RERANKER_MODEL_NAME` | `none`, `keyword-overlap`, local reranker model names | deployment-specific model names | Included in cache keys/metrics when reranking is enabled. |
| `LOCAL_RERANKER_BASE_URL` | local HTTP URL | deployment-specific endpoints | Used when `LOCAL_RERANKER_RUNTIME=cross-encoder` or `vllm`. |
| `LOCAL_RERANKER_REQUEST_TIMEOUT_SECONDS` | positive number | adapter-specific timeouts | Used by local HTTP reranker clients. |
| `RERANKER_CANDIDATE_MULTIPLIER` | positive integer | adapter-tuned values | Controls how many initial candidates are retrieved before final top-k reranking. |
| `RETRIEVAL_LATENCY_WARNING_MS` | positive number | deployment-specific SLOs | Drives analytics/model-status warning displays for retrieval latency. |
| `TOTAL_LATENCY_WARNING_MS` | positive number | deployment-specific SLOs | Drives model-status warning displays for end-to-end query latency. |
| `LOCAL_MODEL_REQUEST_TIMEOUT_SECONDS` | positive number | adapter-specific timeouts | Used by Ollama/vLLM HTTP clients. |
| `LOCAL_MODEL_PROFILE` | `custom`, `local-default`, `host-ollama`, `compose-ollama`, `vllm-gpu` | deployment-specific profile names | Applies a tested local profile before provider construction. `custom` leaves individual settings unchanged. |
| `LOCAL_MODEL_GPU_PROFILE` | `none` or a deployment label | GPU-specific values | Informational today; reported by model status/UI so operators can label GPU deployments. |
| `LLM_PROVIDER` | `local`, `openai` | additional public token-based providers | `openai` uses the public OpenAI-compatible chat-completions adapter and requires `PUBLIC_LLM_ENABLED=true`. |
| `LOCAL_LLM_RUNTIME` | `extractive`, `ollama`, `vllm` | adapter-specific runtimes | `extractive` selects sentences from authorized chunks; `ollama` calls `/api/generate`; `vllm` calls OpenAI-compatible `/v1/chat/completions`. |
| `LOCAL_LLM_MODEL_NAME` | `extractive`, any installed Ollama generation model | local model names | Sent as `model` for Ollama; included in metrics/cache keys. |
| `PUBLIC_LLM_ENABLED` | `false`, `true` | policy-controlled deployment values | Keeps external API usage opt-in. Public adapters fail closed unless this is `true`. |
| `PUBLIC_LLM_BASE_URL` | OpenAI-compatible base URL | deployment-specific public endpoints | Used by public embedding and answer-generation adapters. Defaults to `https://api.openai.com`. |
| `PUBLIC_LLM_API_KEY` | non-empty token when public providers are enabled | secret-manager values | Sent as a bearer token by public provider adapters. Keep this out of source control. |
| `PUBLIC_LLM_MODEL_NAME` | chat/generation model name | approved deployment model names | Required when `LLM_PROVIDER=openai`. |
| `PUBLIC_EMBEDDING_MODEL_NAME` | embedding model name | approved deployment model names | Required when `EMBEDDING_PROVIDER=openai`. |

If `RERANKER_PROVIDER=local` is selected with `LOCAL_RERANKER_RUNTIME=cross-encoder` or `vllm`, the app expects `LOCAL_RERANKER_BASE_URL` to expose `POST /rerank` with `query`, `documents`, `model`, and `top_n`, returning either `results` entries with `index` and `relevance_score` or a numeric `scores` array.

## Packaged Local Profiles

`LOCAL_MODEL_PROFILE` is the quickest way to switch between known local-open-source deployments while keeping `PUBLIC_LLM_ENABLED=false`.

| Profile | Use case | Applied settings |
| --- | --- | --- |
| `custom` | Manual configuration | Leaves all individual runtime/model/base URL settings unchanged. |
| `local-default` | No-download deterministic demos/tests | Hashing embeddings, extractive answers, no reranker. |
| `host-ollama` | Backend/worker in Docker, Ollama running on the Mac | Ollama embeddings/generation through `http://host.docker.internal:11434`, with `nomic-embed-text:latest` and `llama3.1:8b`. |
| `compose-ollama` | Ollama running as the optional Compose service | Ollama embeddings/generation through `http://ollama:11434`, with `nomic-embed-text` and `llama3.1`. |
| `vllm-gpu` | Local GPU/OpenAI-compatible endpoints | vLLM embeddings/generation through `http://host.docker.internal:8000` plus a local reranker endpoint at `http://host.docker.internal:8081`. |

Example for Mac-host Ollama from Docker:

```text
LOCAL_MODEL_PROFILE=host-ollama
PUBLIC_LLM_ENABLED=false
```

Example for a local vLLM GPU service:

```text
LOCAL_MODEL_PROFILE=vllm-gpu
LOCAL_MODEL_GPU_PROFILE=single-gpu
PUBLIC_LLM_ENABLED=false
```

Profiles can still be overridden later by returning to `LOCAL_MODEL_PROFILE=custom` and setting individual runtime values.

For deployment commands and the separate vLLM GPU Compose example, see [Local Model Deployment](local-model-deployment.md).

## Vector Indexing And Reranking

The query pipeline asks the configured vector index for tenant-safe candidates before hybrid scoring. Defaults use the in-memory vector index and deterministic hashing embeddings. When `VECTOR_INDEX_BACKEND=pgvector` and `ENABLE_DB_PERSISTENCE=true`, ingestion writes chunk embeddings to `document_chunks.embedding`, and query retrieval orders candidates with pgvector before the existing keyword/early-term/hybrid score is applied. `VECTOR_INDEX_BACKEND=qdrant` writes/searches vectors in Qdrant using RBAC metadata payload filters plus the application-level authorization check.

Check and backfill persisted chunks after changing vector backends or embedding models:

```bash
python -m app.rag.vector_ops
```

The reranker boundary runs after initial retrieval. The default `RERANKER_PROVIDER=none` returns the existing order unchanged while adding provider/runtime/model names to cache keys and metrics. `RERANKER_PROVIDER=local` with `LOCAL_RERANKER_RUNTIME=keyword` applies a deterministic local keyword-overlap rerank step. `LOCAL_RERANKER_RUNTIME=cross-encoder` and `LOCAL_RERANKER_RUNTIME=vllm` call a local HTTP rerank service so heavier local rerankers can be added without public token-based providers.

## vLLM-Compatible Local Services

For embeddings through an OpenAI-compatible local server:

```text
LOCAL_EMBEDDING_RUNTIME=vllm
LOCAL_EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
LOCAL_EMBEDDING_BASE_URL=http://localhost:8000
```

For answer generation:

```text
LOCAL_LLM_RUNTIME=vllm
LOCAL_LLM_MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.3
LOCAL_LLM_BASE_URL=http://localhost:8000
```

The embedding adapter calls `POST /v1/embeddings`; the answer adapter calls `POST /v1/chat/completions`.

## Public OpenAI-Compatible Providers

Public token-based providers are implemented but disabled by default. They should only be enabled after deployment policy approval, secret-management setup, and cost/rate-limit review.

Use local embeddings with public answer generation:

```text
PUBLIC_LLM_ENABLED=true
LLM_PROVIDER=openai
PUBLIC_LLM_BASE_URL=https://api.openai.com
PUBLIC_LLM_API_KEY=...
PUBLIC_LLM_MODEL_NAME=<approved-chat-model>
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_RUNTIME=hashing
```

Use public embeddings and public answer generation:

```text
PUBLIC_LLM_ENABLED=true
EMBEDDING_PROVIDER=openai
PUBLIC_EMBEDDING_MODEL_NAME=<approved-embedding-model>
LLM_PROVIDER=openai
PUBLIC_LLM_MODEL_NAME=<approved-chat-model>
PUBLIC_LLM_API_KEY=...
```

The public embedding adapter calls `POST /v1/embeddings`, the answer adapter calls `POST /v1/chat/completions`, and both send `Authorization: Bearer <PUBLIC_LLM_API_KEY>`. `/api/v1/model-status` checks configuration only; it does not call the public API.

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
LOCAL_MODEL_PROFILE=host-ollama
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
LOCAL_MODEL_PROFILE=host-ollama
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
LOCAL_MODEL_PROFILE=compose-ollama
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
LOCAL_MODEL_PROFILE=host-ollama
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

The Redis query cache key also includes provider, runtime, and model names. Changing model settings therefore creates a new cache entry instead of reusing an answer generated under a previous runtime. Public-provider cache keys include `openai-compatible` runtime labels and the configured public model names.

## Runtime Status

Authenticated users can inspect the active model configuration through:

```text
GET /api/v1/model-status
```

The response reports the configured model profile, GPU profile label, embedding, answer, vector-index, and reranker providers/runtimes, model names, readiness, local endpoint URLs when relevant, and performance warning thresholds. Hashing embeddings, extractive answer generation, the memory vector index, and disabled/keyword rerankers report ready without network calls. Ollama runtimes perform a lightweight `GET /api/tags` readiness check and mark the component not ready when Ollama is unreachable or the configured model has not been pulled. Qdrant vector-index status checks the configured collection and reports attention when Qdrant is unreachable or the collection has not been created/backfilled.

The React console uses this endpoint to show the model readiness pill and the active profile, embedding, answer, vector-index, reranker, and latency-threshold cards.

Ollama, vLLM, and public OpenAI-compatible query-time failures raise `ModelProviderRequestError` with the operation, model name, endpoint, and HTTP status or timeout class. The query API converts those provider errors into `503 Service Unavailable` responses so callers see a clear model-provider readiness issue instead of a generic server failure.

## Evaluation Behavior

`python -m app.eval.run` still uses the same extractive answer generator as the default local provider. This keeps the retrieval quality gate aligned with the production query path while avoiding network calls or model downloads.

## Adding A Future Local Adapter

When adding more local model support:

1. Implement an `EmbeddingModel`, an `AnswerGenerator`, or both in `app/rag/model_providers.py` or a focused submodule.
2. Use `LOCAL_EMBEDDING_BASE_URL` and `LOCAL_LLM_BASE_URL` for local service endpoints.
3. Keep `PUBLIC_LLM_ENABLED=false`; local adapters should not require public token-based APIs.
4. Add tests for config selection, adapter failure modes, status checks, cache-key separation, and query metrics.
5. Run `python3 -m pytest`, `python3 -m app.eval.run`, `npm run build`, and `docker compose config`.

## Adding Another Public Adapter

When adding another public token-based provider:

1. Keep the provider behind `PUBLIC_LLM_ENABLED=true`.
2. Add provider-specific API key/base URL/model settings.
3. Do not call public APIs from `/api/v1/model-status`; report configuration readiness only.
4. Add tests for gate enforcement, missing secrets, request shape, authorization headers, error details, cache-key separation, and query metrics.
5. Update deployment docs with secret-manager guidance before enabling the provider in any environment.
