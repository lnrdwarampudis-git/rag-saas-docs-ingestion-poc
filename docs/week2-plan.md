# Week 2 Target Plan

## Goal

Complete the first usable RAG pipeline and Redis cache layer so the Week 3 UI can query uploaded documents and display answers, citations, and latency metrics.

## Delivered In This Scaffold

1. Query API
   - `POST /api/v1/query`
   - Accepts tenant, query, roles, and `top_k`
   - Returns answer, citations, cache status, and metrics

2. Retrieval
   - RBAC-aware filtering before ranking
   - Hybrid ranking baseline using deterministic vector similarity plus keyword overlap
   - Top-k citation output

3. Cache
   - Redis-backed query cache
   - In-memory fallback for local development
   - Cache key includes tenant, roles, query, and top-k

4. Model Interfaces
   - Local deterministic embedding model for tests and development
   - Clear production swap point for BGE/E5/Mixedbread embeddings
   - Clear production swap point for vLLM/Ollama answer generation

## Week 2 Exit Criteria

- Ingested chunks can be queried through `/api/v1/query`.
- Query responses include citations with document id, file name, chunk index, score, and OCR metadata.
- Unauthorized role-restricted chunks are filtered before ranking.
- Repeated equivalent queries are served from cache.
- Unit tests cover retrieval, RBAC filtering, and cache behavior.

## Production Follow-Ups

- Persist chunks and embeddings to PostgreSQL/Qdrant instead of in-memory store.
- Add Celery workers for extraction, chunking, embedding, and indexing.
- Add a reranker model after initial retrieval benchmarks.
- Replace deterministic embeddings with an open source embedding service.
- Replace extractive placeholder answer composition with vLLM/Ollama generation.
- Add OpenTelemetry metrics for cache hit ratio, retrieval latency, and generation latency.
