# Week 4 Target Plan

## Goal

Complete Docker containerization and testing coverage so the RAG SaaS MVP can be run as a composed system and verified through unit, API E2E, and frontend smoke tests.

## Delivered In This Scaffold

1. Containerization
   - Backend Dockerfile with OCR/runtime dependencies
   - Frontend Dockerfile with static nginx runtime
   - nginx reverse proxy for `/api` and `/health`
   - Docker Compose services for frontend and backend
   - Existing PostgreSQL, Redis, MinIO, Qdrant, and Keycloak services retained

2. Unit and API Testing
   - Existing chunking, parser, retrieval, cache, and pipeline tests retained
   - API E2E tests added for ingest-then-query
   - API E2E test added for role-restricted retrieval filtering

3. Frontend E2E Testing
   - Playwright configured
   - UI smoke tests added for workspace rendering
   - Interaction test added for query button enablement

4. Security and Build Verification
   - Frontend production build
   - npm audit verification
   - Docker ignore rules for clean build contexts

## Week 4 Commands

```bash
python3 -m pytest

cd frontend
npm install
npm run build
npm audit --audit-level=moderate
npx playwright install chromium
npm run test:e2e

cd ..
docker compose up --build
```

## Week 4 Exit Criteria

- Backend unit and API E2E tests pass.
- Frontend TypeScript production build passes.
- Frontend dependency audit reports no moderate-or-higher vulnerabilities.
- Playwright UI smoke tests pass.
- `docker compose up --build` starts frontend, backend, PostgreSQL, Redis, MinIO, Qdrant, and Keycloak.
- Week 6 extends Compose with a `worker` service for background ingestion jobs.
- Frontend is reachable at `http://127.0.0.1:5173`.
- Backend health endpoint is reachable at `http://127.0.0.1:8000/health`.

## Remaining Production Hardening

- Replace local-path ingestion with real multipart uploads to MinIO.
- ~~Add Keycloak realm import and JWT validation middleware.~~ Done -- see [Architecture: Authentication, Authorization And Session Management](architecture.md#authentication-authorization-and-session-management).
- Persist document chunks and embeddings to PostgreSQL/Qdrant.
- ~~Add a worker container for OCR/chunking/embedding-style ingestion jobs.~~ Done as a Redis-polled POC worker -- see [Week 6 Suggested Target Plan](week6-plan.md).
- Add load tests for TTFT, P95 API latency, retrieval latency, and cache hit ratio.
