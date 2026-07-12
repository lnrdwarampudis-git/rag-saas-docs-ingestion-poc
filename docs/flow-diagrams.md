# Flow Diagrams

These diagrams are editable Mermaid text and render directly in GitHub. The top-level component map stays in [Architecture](architecture.md); this file focuses on request and data movement.

## Authentication And Session Flow

```mermaid
sequenceDiagram
  actor User
  participant UI as React/Vite SPA
  participant KC as Keycloak
  participant API as FastAPI
  participant DB as PostgreSQL RBAC

  User->>UI: Open app
  UI->>API: GET /api/v1/auth/config
  API-->>UI: issuer, client_id, audience
  User->>UI: Sign in with Keycloak
  UI->>UI: Generate PKCE verifier/challenge
  UI->>KC: Authorization redirect
  KC->>User: Login form
  User->>KC: Demo username/password
  KC-->>UI: Authorization code
  UI->>KC: Exchange code + verifier
  KC-->>UI: Access token + refresh token
  UI->>API: GET /api/v1/auth/me with bearer token
  API->>KC: Fetch JWKS when cache misses
  API->>API: Verify signature, issuer, audience, expiry
  API->>DB: Resolve tenant and roles by keycloak_subject
  DB-->>API: app_user, tenant, roles
  API-->>UI: Authenticated member profile
  UI->>KC: Refresh token before access token expiry
```

## Background Ingestion Flow

```mermaid
sequenceDiagram
  actor Member
  participant UI as React/Vite UI
  participant API as FastAPI Documents API
  participant DB as PostgreSQL
  participant Redis as Redis Queue
  participant Worker as app.worker
  participant Parser as Parser/OCR/Chunker
  participant Vector as pgvector/Qdrant Ready Index

  Member->>UI: Select file and click "Upload to queue"
  UI->>API: POST /api/v1/documents/upload-async
  API->>API: Validate bearer token and resolve tenant/roles
  API->>API: Save upload under UPLOAD_DIR
  API->>DB: Insert pending document + queued processing_jobs row
  API->>Redis: RPUSH rag:processing-jobs job_id
  API-->>UI: 202 Accepted with job_id + document_id
  UI->>API: Poll GET /api/v1/processing-jobs/{job_id}
  Worker->>Redis: BLPOP rag:processing-jobs
  Redis-->>Worker: job_id
  Worker->>DB: Load job and document context
  Worker->>DB: Mark job processing, increment attempts
  Worker->>Parser: Extract text, OCR when needed, chunk with metadata
  Parser-->>Worker: chunks + extraction warnings
  Worker->>DB: Upsert document, chunks, audit event
  Worker->>Vector: Embedding/index step ready for pgvector/Qdrant
  Worker->>DB: Mark job completed or failed
  UI->>API: Poll job status
  API->>DB: Read processing_jobs for caller tenant
  API-->>UI: completed or failed
  UI->>API: GET /api/v1/documents/{document_id}
  API-->>UI: Authorized document detail + chunk preview
```

## Authorized Query Flow

```mermaid
flowchart TD
  member["Authenticated Member"] --> queryUi["Query Panel"]
  queryUi --> queryApi["POST /api/v1/query"]
  queryApi --> token["JWT Validation"]
  token --> rbac["Tenant + Role Resolution"]
  rbac --> cacheKey["Identity-Scoped Cache Key"]
  cacheKey --> redis{"Redis Cache Hit?"}
  redis -- yes --> answer["Return Cached Answer"]
  redis -- no --> chunks["Load Candidate Chunks"]
  chunks --> filter["RBAC Chunk Filter<br/>tenant, role, private owner"]
  filter --> embed["Embedding Provider<br/>local hashing default"]
  embed --> rank["Hybrid Retrieval + Ranking"]
  rank --> threshold["Precision Thresholds<br/>min score + keyword overlap"]
  threshold --> compose["Answer Provider<br/>extractive default"]
  compose --> saveCache["Store Redis Answer"]
  saveCache --> answer
```

## Retrieval Evaluation Flow

```mermaid
flowchart TD
  dataset["data/eval/retrieval_cases.json"] --> runner["python -m app.eval.run"]
  runner --> retriever["Hybrid Retriever"]
  retriever --> citations["Retrieved document ids + scores"]
  runner --> answer["Extractive Answer Generator"]
  answer --> relevance["Expected answer term checks"]
  citations --> precision["Context Precision"]
  citations --> recall["Context Recall"]
  relevance --> report["Eval Report<br/>pass/fail against KPI targets"]
  precision --> report
  recall --> report
```

## Model Provider Strategy

```mermaid
flowchart LR
  config["Settings"] --> embeddingProvider["EMBEDDING_PROVIDER"]
  config --> llmProvider["LLM_PROVIDER"]
  embeddingProvider --> localEmbedding{"local"}
  localEmbedding --> hashing["Current hashing embeddings"]
  localEmbedding --> futureEmbedding["Future Ollama/vLLM or BGE/E5 adapter"]
  llmProvider --> localLlm{"local"}
  localLlm --> extractive["Current extractive generator"]
  localLlm --> futureLlm["Future Ollama/vLLM generator"]
  llmProvider --> public{"public provider later"}
  public --> gate["PUBLIC_LLM_ENABLED=true required"]
  gate --> tokenApi["Token/API-based LLM provider"]
  hashing --> cacheKey["Provider/runtime/model names<br/>included in cache key + metrics"]
  extractive --> cacheKey
```

## RBAC Visibility Rules

```mermaid
flowchart LR
  doc["Document / Chunk"] --> tenantCheck{"Same Tenant?"}
  tenantCheck -- no --> deny["Deny / hide as 404"]
  tenantCheck -- yes --> visibility{"Visibility"}
  visibility -- tenant --> allow["Allow tenant member"]
  visibility -- role --> roleCheck{"Any allowed role?"}
  roleCheck -- yes --> allow
  roleCheck -- no --> deny
  visibility -- private --> ownerCheck{"Uploaded by caller?"}
  ownerCheck -- yes --> allow
  ownerCheck -- no --> deny
```

## Docker Runtime Flow

```mermaid
flowchart TD
  browser["Browser http://127.0.0.1:5173"] --> frontend["frontend nginx"]
  frontend --> backend["backend FastAPI :8000"]
  backend --> postgres[("PostgreSQL :55432 host")]
  backend --> redis[("Redis")]
  backend --> keycloak["Keycloak :8080"]
  backend --> qdrant[("Qdrant")]
  backend --> minio[("MinIO")]
  backend --> uploads["/data/uploads bind mount"]
  worker["worker python -m app.worker"] --> redis
  worker --> postgres
  worker --> uploads
  worker --> qdrant
  worker --> minio
```
