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
LLM_PROVIDER=local
LOCAL_LLM_RUNTIME=extractive
LOCAL_LLM_MODEL_NAME=extractive
LOCAL_LLM_BASE_URL=http://localhost:11434
PUBLIC_LLM_ENABLED=false
```

`LOCAL_*_BASE_URL` values are present now so later Ollama/vLLM adapters can use the same configuration shape. The default hashing and extractive runtimes do not call those URLs.

## Supported Values Today

| Setting | Supported now | Reserved for later | Notes |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local` | public/provider-specific services | Non-local values fail fast today. |
| `LOCAL_EMBEDDING_RUNTIME` | `hashing` | `ollama`, `vllm` | `hashing` uses the deterministic in-process embedding baseline. |
| `LOCAL_EMBEDDING_MODEL_NAME` | `hashing-384` | BGE, E5, Mixedbread, or adapter model names | Informational for the hashing runtime and included in metrics/cache keys. |
| `EMBEDDING_DIMENSIONS` | integer dimension count practical for local ranking | adapter-specific dimensions | Default is `384`; keep it greater than zero for hashing embeddings. |
| `LLM_PROVIDER` | `local` | public token-based providers | Public providers require `PUBLIC_LLM_ENABLED=true` and adapter code. |
| `LOCAL_LLM_RUNTIME` | `extractive` | `ollama`, `vllm` | `extractive` selects sentences from authorized retrieved chunks. |
| `LOCAL_LLM_MODEL_NAME` | `extractive` | local model names | Included in metrics/cache keys. |
| `PUBLIC_LLM_ENABLED` | `false` | `true` after policy approval and adapter implementation | Keeps external API usage opt-in. |

If `LOCAL_EMBEDDING_RUNTIME=ollama`, `LOCAL_EMBEDDING_RUNTIME=vllm`, `LOCAL_LLM_RUNTIME=ollama`, or `LOCAL_LLM_RUNTIME=vllm` is set before the adapters exist, startup/query construction raises `ModelProviderConfigurationError`. That failure is deliberate: it prevents silently falling back to a different model path.

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

## Evaluation Behavior

`python -m app.eval.run` still uses the same extractive answer generator as the default local provider. This keeps the retrieval quality gate aligned with the production query path while avoiding network calls or model downloads.

## Adding A Future Local Adapter

When adding Ollama or vLLM support:

1. Implement an `EmbeddingModel`, an `AnswerGenerator`, or both in `app/rag/model_providers.py` or a focused submodule.
2. Use `LOCAL_EMBEDDING_BASE_URL` and `LOCAL_LLM_BASE_URL` for local service endpoints.
3. Keep `PUBLIC_LLM_ENABLED=false`; local adapters should not require public token-based APIs.
4. Add tests for config selection, adapter failure modes, cache-key separation, and query metrics.
5. Run `python3 -m pytest`, `python3 -m app.eval.run`, `npm run build`, and `docker compose config`.

Public token-based providers should be added only after deployment policy allows external API usage, and should remain gated behind `PUBLIC_LLM_ENABLED=true`.
