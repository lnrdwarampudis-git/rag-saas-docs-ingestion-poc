# Week 7 Suggested Target Plan

## Goal

Make RAG answer quality measurable and improve precision before adding heavier local LLM or reranker dependencies.

## Delivered Scope

1. Offline evaluation dataset
   - Added `data/eval/retrieval_cases.json`.
   - Covers knowledge representation retrieval, Redis cache relevance, and RBAC role filtering.

2. Evaluation runner
   - Added `python -m app.eval.run`.
   - Reports context precision, context recall, answer relevance, pass/fail counts, retrieved document ids, and generated answer text.

3. Retrieval guardrails
   - Added configurable minimum retrieval score and keyword-overlap threshold.
   - Citations now include keyword, vector, and early-term score components for debugging.

4. Local-model-first strategy
   - Added config flags for `LLM_PROVIDER`, `LOCAL_LLM_RUNTIME`, and `PUBLIC_LLM_ENABLED`.
   - Default remains local/offline and deterministic.
   - Public token-based LLMs are documented as a later optional provider path.

## Exit Criteria

- `python -m app.eval.run` passes the quality targets.
- Backend tests pass.
- Query responses include retrieval guardrail metrics.
- Documentation explains the local/open-source model path and later public provider option.

## Follow-Ups

- Add more evaluation cases from uploaded PDFs, DOCX, XLSX, and PPTX files.
- Persist eval run reports to `outputs/` or Postgres for trend tracking.
- Add a local open-source embedding service, such as BGE, E5, or Mixedbread.
- Add a local reranker, such as BGE reranker.
- Add Ollama or vLLM for local answer generation.
- Add optional public token-based LLM provider adapters only after local/provider abstraction is stable.
