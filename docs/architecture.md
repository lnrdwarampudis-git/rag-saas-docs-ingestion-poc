# Architecture

This architecture diagram is editable Mermaid text and renders directly in GitHub. Update the diagram by editing the Mermaid block below.

```mermaid
flowchart LR
  %% Client layer
  subgraph client["Client Layer"]
    browser["User Browser"]
    ui["React/Vite UI<br/>Upload, query, citations, metrics"]
  end

  %% Edge and API
  subgraph api["API Layer"]
    nginx["Nginx Static Host<br/>2 GB upload limit"]
    fastapi["FastAPI Backend<br/>OpenAPI, validation, orchestration"]
    authz["RBAC Filter<br/>tenant, visibility, role checks"]
  end

  %% Identity
  subgraph identity["Identity And Access"]
    keycloak["Keycloak<br/>OIDC/JWT, users, roles"]
  end

  %% Ingestion pipeline
  subgraph ingestion["Document Ingestion Pipeline"]
    upload["Upload Or Mounted Path"]
    parser["Parser Layer<br/>PDF, DOCX, XLSX, TXT"]
    ocr["OCR Path<br/>Tesseract ready"]
    chunker["Chunking Strategy<br/>token target, overlap, metadata"]
    embed["Embedding Step<br/>open-source model target"]
  end

  %% Retrieval pipeline
  subgraph retrieval["RAG Query Pipeline"]
    query["Authorized Query"]
    cache["Redis Query Cache<br/>cache key, TTL"]
    retriever["Hybrid Retriever<br/>keyword + vector score"]
    ranker["Precision Ranking<br/>definition/early-term boost"]
    answer["Answer Composer<br/>citations, latency metrics"]
  end

  %% Data plane
  subgraph data["Data Layer"]
    postgres[("PostgreSQL + pgvector<br/>tenants, users, roles<br/>documents, chunks, audit logs")]
    qdrant[("Qdrant<br/>vector search option")]
    minio[("MinIO<br/>original files and extracted text")]
    audit[("Audit Logs<br/>ingestion and access events")]
  end

  %% Observability and testing
  subgraph ops["Ops And Validation"]
    docker["Docker Compose<br/>local full stack"]
    tests["Pytest + Playwright<br/>unit, API E2E, UI smoke"]
    logs["Application Logs<br/>request, ingestion, persistence"]
  end

  browser --> ui
  ui --> nginx
  nginx --> fastapi
  fastapi -. validate token .-> keycloak
  fastapi --> authz

  ui --> upload
  upload --> fastapi
  fastapi --> parser
  parser --> ocr
  parser --> chunker
  ocr --> chunker
  chunker --> embed
  embed --> postgres
  embed --> qdrant
  fastapi --> minio
  fastapi --> audit
  audit --> postgres

  ui --> query
  query --> fastapi
  fastapi --> cache
  cache -- hit --> answer
  cache -- miss --> retriever
  retriever --> postgres
  retriever --> qdrant
  retriever --> authz
  authz --> ranker
  ranker --> answer
  answer --> cache
  answer --> ui

  docker --> nginx
  docker --> fastapi
  docker --> postgres
  docker --> redis["Redis"]
  docker --> minio
  docker --> qdrant
  docker --> keycloak
  tests --> fastapi
  tests --> ui
  fastapi --> logs

  classDef client fill:#e8f3ff,stroke:#2563eb,color:#0f172a;
  classDef service fill:#f7fee7,stroke:#65a30d,color:#172554;
  classDef data fill:#fff7ed,stroke:#ea580c,color:#1f2937;
  classDef security fill:#fef2f2,stroke:#dc2626,color:#111827;
  classDef ops fill:#f5f3ff,stroke:#7c3aed,color:#111827;

  class browser,ui client;
  class nginx,fastapi,upload,parser,ocr,chunker,embed,query,cache,retriever,ranker,answer service;
  class postgres,qdrant,minio,audit data;
  class keycloak,authz security;
  class docker,tests,logs ops;
```

## Request Flow

1. Users upload documents or provide a mounted path through the React/Vite UI.
2. FastAPI validates the request, extracts text from supported document types, invokes OCR when needed, and chunks the extracted text.
3. Chunks are enriched with tenant, document, visibility, role, OCR, and source metadata.
4. Metadata and chunks are persisted in PostgreSQL. Qdrant is included as the vector search option for scale-oriented retrieval.
5. Users ask questions through the query panel.
6. Redis is checked for cached answers. On cache miss, retrieval runs against authorized chunks, applies RBAC filters, ranks contexts, and composes an answer with citations and latency metrics.

## Component Responsibilities

- React/Vite UI: document upload, mounted-path ingestion, tenant/role input, query form, citations, cache status, and latency display.
- FastAPI backend: request validation, ingestion orchestration, retrieval orchestration, persistence, and API contracts.
- Keycloak: target identity provider for OAuth/OIDC, JWT validation, and member roles.
- PostgreSQL + pgvector: tenant metadata, RBAC tables, document records, chunk records, and audit logs.
- Redis: query cache and future queue/rate-limit support.
- MinIO: target object storage for original files and extracted text.
- Qdrant: optional vector index for higher-scale retrieval experiments.
- Docker Compose: local reproducible stack for the POC.

## Editable Diagram Notes

- GitHub renders Mermaid blocks automatically in Markdown.
- The diagram can be copied into Mermaid Live Editor or diagrams.net Mermaid import for visual editing.
- Keep infrastructure-specific host paths out of this file; use `.env` for local overrides.
