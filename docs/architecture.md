# Architecture

This architecture diagram is editable Mermaid text and renders directly in GitHub. Update the diagram by editing the Mermaid block below.

```mermaid
flowchart LR
  %% Client layer
  subgraph client["Client Layer"]
    browser["User Browser"]
    ui["React/Vite UI<br/>workspace, upload, query, citations"]
    loginScreen["Login Screen<br/>Sign in with Keycloak (PKCE)"]
    aaScreen["A&A Panel<br/>signed-in user, tenant, roles (read-only)"]
    sessionScreen["Session Panel<br/>stateless JWT, silent refresh, sign out"]
    formatsScreen["Format Intake Screen<br/>PDF, Word, Excel, PowerPoint, text, images"]
  end

  %% Edge and API
  subgraph api["API Layer"]
    nginx["Nginx Static Host<br/>2 GB upload limit"]
    fastapi["FastAPI Backend<br/>OpenAPI, validation, orchestration"]
    authApi["Auth API<br/>GET /auth/config, GET /auth/me"]
    jwtValidate["get_current_user dependency<br/>verify signature, issuer, audience, expiry"]
    rbacResolve["RBAC Resolver<br/>Postgres-first, token-claims fallback"]
    authz["RBAC Filter<br/>tenant, visibility, role checks"]
  end

  %% Identity
  subgraph identity["Authentication And Authorization"]
    keycloak["Keycloak<br/>realm: rag"]
    pkceFlow["rag-frontend client<br/>Authorization Code + PKCE"]
    jwks["JWKS Endpoint<br/>/certs (cached, signing key only)"]
    demoUsers["Demo Users + Roles<br/>admin, finance, engineering, legal, support"]
  end

  %% Ingestion pipeline
  subgraph ingestion["Document Ingestion Pipeline"]
    upload["Upload Or Mounted Path"]
    office["Microsoft Office<br/>Word DOCX, Excel XLSX, PowerPoint PPTX"]
    pdf["PDF Documents<br/>native text or OCR path"]
    textFiles["Text Formats<br/>TXT, MD, CSV, TSV"]
    images["Image Documents<br/>PNG, JPG, TIFF, BMP"]
    parser["Parser Layer<br/>Office, PDF, text, image"]
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
    postgres[("PostgreSQL + pgvector<br/>tenants, app_users, roles, user_roles<br/>documents, chunks, audit logs")]
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
  ui -- unauthenticated --> loginScreen
  loginScreen -- redirect with code_challenge --> keycloak
  keycloak --> pkceFlow
  pkceFlow --> demoUsers
  keycloak -- authorization code --> ui
  ui -- code_verifier --> keycloak
  keycloak -- access + refresh token --> ui
  ui --> aaScreen
  ui --> sessionScreen
  ui --> formatsScreen
  ui -- Bearer token --> nginx
  nginx --> fastapi
  fastapi --> authApi
  fastapi --> jwtValidate
  jwtValidate -. fetch signing key .-> jwks
  jwks --> keycloak
  jwtValidate --> rbacResolve
  rbacResolve -- keycloak_subject lookup --> postgres
  rbacResolve -. DB unreachable: fallback to tenant_id claim .-> jwtValidate
  fastapi --> authz
  rbacResolve --> authz

  ui --> upload
  upload --> fastapi
  office --> parser
  pdf --> parser
  textFiles --> parser
  images --> ocr
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

  class browser,ui,loginScreen,aaScreen,sessionScreen,formatsScreen client;
  class nginx,fastapi,authApi,upload,office,pdf,textFiles,images,parser,ocr,chunker,embed,query,cache,retriever,ranker,answer service;
  class postgres,qdrant,minio,audit data;
  class keycloak,pkceFlow,jwks,demoUsers,jwtValidate,rbacResolve,authz security;
  class docker,tests,logs ops;
```

## Request Flow

1. An unauthenticated user hits the Login Screen and clicks "Sign in with Keycloak." The frontend generates a PKCE code verifier/challenge, redirects to Keycloak's authorization endpoint, and exchanges the returned code (plus verifier) for an access + refresh token directly with Keycloak -- no backend involvement in the login itself.
2. Every subsequent API call attaches the access token as `Authorization: Bearer <token>`. FastAPI's `get_current_user` dependency validates the token's signature (against Keycloak's cached JWKS), issuer, audience, and expiry before any route body runs.
3. The RBAC Resolver looks up the caller's `tenant_id` and roles from PostgreSQL (`app_users` / `roles` / `user_roles`, keyed by the token's `sub`), falling back to a `tenant_id` token claim and `realm_access.roles` only if the database is unreachable. Request bodies can no longer supply their own `tenant_id` or roles.
4. Users upload documents or provide a mounted path through the React/Vite UI; `tenant_id` and the uploader's identity are taken from the resolved identity, not the request.
5. FastAPI extracts text from supported document types, invokes OCR when needed, and chunks the extracted text. Chunks are enriched with tenant, document, visibility, role, owner, and source metadata.
6. Metadata and chunks are persisted in PostgreSQL. Qdrant is included as the vector search option for scale-oriented retrieval.
7. Users ask questions through the query panel; `tenant_id` and roles again come from the resolved identity.
8. Redis is checked for cached answers (the cache key includes the requester's identity so private-document results never leak across users). On cache miss, retrieval runs against authorized chunks, applies RBAC filters (tenant match, then tenant/role/private-owner visibility), ranks contexts, and composes an answer with citations and latency metrics.
9. Access tokens are short-lived and stateless (no server-side session store); the frontend silently refreshes them in the background via Keycloak's refresh-token grant and clears its session if the refresh fails, dropping the user back to the Login Screen.

## Component Responsibilities

- React/Vite UI: PKCE login/logout, document upload, mounted-path ingestion, read-only A&A and session status display, query form, citations, cache status, and latency display.
- FastAPI backend: bearer-token validation, RBAC resolution, request validation, ingestion orchestration, retrieval orchestration, persistence, and API contracts.
- Keycloak: identity provider for OAuth/OIDC (Authorization Code + PKCE for the SPA), issues and refreshes JWTs, exposes the JWKS used to validate them, and owns realm roles and demo users.
- PostgreSQL + pgvector: tenant metadata, RBAC tables (`app_users`, `roles`, `user_roles`) as the source of truth for tenant/role resolution, document records, chunk records, and audit logs.
- Redis: query cache and future queue/rate-limit support.
- MinIO: target object storage for original files and extracted text.
- Qdrant: optional vector index for higher-scale retrieval experiments.
- Docker Compose: local reproducible stack for the POC, including a `--import-realm` Keycloak boot that seeds the `rag` realm from `infra/keycloak/realm-export.json`.

## Authentication, Authorization And Session Management

- **Login**: Authorization Code + PKCE against Keycloak's `rag-frontend` public client. No client secret is used or needed.
- **Token validation**: `app/auth/tokens.py` verifies signature (RS256, via a cached JWKS lookup by `kid`), `iss`, `aud`, and `exp` on every request. Keycloak's JWKS includes both a signing key (`use=sig`) and an encryption key (`use=enc`); only the signing key is used to validate tokens.
- **Authorization (RBAC)**: `app/auth/service.py` resolves tenant and roles from Postgres by `keycloak_subject`, falling back to a `tenant_id` custom claim and `realm_access.roles` if the database is unreachable. `require_roles(...)` gates specific endpoints; chunk-level visibility (`tenant`, `role`, `private`) is enforced in `app/rag/retrieval.py` for every retrieval and direct chunk lookup.
- **Session management**: stateless JWTs -- there is no server-side session store or logout blacklist. The frontend holds tokens in `sessionStorage` (cleared when the tab closes), refreshes them silently ~30s before expiry via Keycloak's refresh-token grant, and redirects to Keycloak's end-session endpoint on sign-out.
- **Demo identities**: `infra/keycloak/realm-export.json` and `infra/postgres/init.sql` seed matching Keycloak users and Postgres `app_users`/`roles` rows for one demo user per role (`admin-demo`, `finance-demo`, `engineer-demo`, `legal-demo`, `support-demo`; password `Passw0rd!`). See [Setup Guide](setup.md#signing-in-keycloak).

## Supported Document Formats

- PDF: native text extraction with OCR fallback path for scanned/image-backed documents.
- Microsoft Word: DOCX extraction.
- Microsoft Excel: XLSX sheet/cell extraction.
- Microsoft PowerPoint: PPTX slide text extraction.
- Text: TXT, Markdown, CSV, and TSV.
- Images: PNG, JPG, JPEG, TIFF, and BMP through OCR.

Legacy binary Office formats such as DOC, XLS, and PPT should be converted to DOCX, XLSX, or PPTX before ingestion for this POC.

## Editable Diagram Notes

- GitHub renders Mermaid blocks automatically in Markdown.
- The diagram can be copied into Mermaid Live Editor or diagrams.net Mermaid import for visual editing.
- Keep infrastructure-specific host paths out of this file; use `.env` for local overrides.
