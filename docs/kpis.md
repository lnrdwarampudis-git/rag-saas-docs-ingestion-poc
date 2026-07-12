# KPI Measurement Plan

## Latency KPIs

- Time to First Token: target `< 800 ms`
- Total Generation Latency: target `3-5 seconds` for approximately 200 words
- Vector Retrieval Latency: target `< 100 ms`
- LLM Processing Time: target `< 2 seconds`
- P95 API Response Time: target `< 4 seconds`

## Quality KPIs

- Context Precision: target `> 85%`
- Context Recall: target `> 80%`
- Answer Relevance: target `> 85%`

## Processing and Cost KPIs

- Document Processing Time: target `< 15 seconds` for normal-sized documents
- Cache Hit Ratio: target `> 20%`
- Storage Cost per GB: target `< $0.15 / month`

## Instrumentation Needed

- Request ID on every API request
- Structured JSON logs
- Audit event for document upload, extraction, chunking, query, and answer generation
- Metrics timers for extraction, OCR, chunking, embedding, retrieval, reranking, generation, and cache lookup
- Token counters for prompt, completion, and context chunks
