# Retrieval Evaluation

Week 7 adds an offline quality gate for the RAG pipeline. The goal is to measure whether retrieval returns the right authorized chunks before adding heavier local LLMs, rerankers, or public token-based providers.

## Run

```bash
python -m app.eval.run
```

For machine-readable output:

```bash
python -m app.eval.run --json
```

Authenticated users can also fetch the same quality gate through the API:

```text
GET /api/v1/evaluation/retrieval
```

The React console renders this report in the Evaluation panel so demos can show the current pass/fail state, average context precision, context recall, answer relevance, and per-case results without leaving the UI.

## Dataset

Evaluation cases live in:

```text
data/eval/retrieval_cases.json
```

Each case defines:

- `query`
- `tenant_id`
- `role_names`
- test `chunks`
- expected source document ids
- expected answer terms

## Metrics

- Context Precision: percentage of retrieved documents that are expected.
- Context Recall: percentage of expected documents retrieved.
- Answer Relevance: percentage of expected answer terms present in the generated/extractive answer.

Current targets:

- Context Precision >= 0.85
- Context Recall >= 0.80
- Answer Relevance >= 0.85

## Precision Guardrails

The retriever now exposes configurable thresholds:

```text
RETRIEVAL_MIN_SCORE=0.12
RETRIEVAL_MIN_KEYWORD_OVERLAP=0.20
```

These guardrails reduce unrelated context, especially when deterministic/hash embeddings produce weak semantic similarity. This directly protects questions such as "What is knowledge representation?" from being answered with unrelated machine-learning scaler text.

## Model Strategy

The POC stays local/open-source first:

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

The default local runtimes are deterministic so tests and demos run without model downloads. `LOCAL_EMBEDDING_RUNTIME=ollama` can be used for local semantic embeddings when an Ollama embedding model is available, and `LOCAL_LLM_RUNTIME=ollama` can be used for local answer generation when an Ollama generation model is available. Future local upgrades should add vLLM embeddings/generation and reranker models such as BGE reranker.

Public token-based LLMs should be added later behind explicit config flags only when deployment policy allows external API usage.

The evaluation runner uses the same extractive answer generator as the default query provider. See [Model Providers](model-providers.md) for the provider interface, supported settings, and cache-key behavior.
