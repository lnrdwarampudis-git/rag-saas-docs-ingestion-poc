# Week 3 Target Plan

## Goal

Complete the UI development milestone so users can ingest documents, set role context, ask questions, inspect citations, and see cache/latency signals.

## Delivered In This Scaffold

1. React/Vite Frontend
   - App shell with sidebar navigation
   - Document ingestion panel
   - Role-aware query workspace
   - Citations panel
   - KPI/latency metrics strip

2. API Integration
   - Calls `POST /api/v1/documents/ingest`
   - Calls `POST /api/v1/query`
   - Displays cache status and query metrics
   - Displays document chunk/citation metadata

3. Access Context
   - Current member role selector
   - Document visibility selector
   - Allowed role selector for role-restricted documents
   - OCR toggle for ingestion

4. Backend Support
   - CORS enabled for local Vite development
   - Vite proxy configured for `/api` and `/health`

## Week 3 Exit Criteria

- UI can start with `npm run dev`.
- Backend can start with `uvicorn app.main:app --reload`.
- User can ingest a local-path document through the UI.
- User can query ingested chunks through the UI.
- Citations, cache status, and latency metrics are visible.
- Role-restricted chunks are hidden from unauthorized role context.

## Production Follow-Ups

- Replace local-path ingestion with browser file upload to MinIO.
- ~~Integrate Keycloak login/logout and JWT propagation.~~ Done -- see [Architecture: Authentication, Authorization And Session Management](architecture.md#authentication-authorization-and-session-management).
- Add processing job status polling.
- Add admin screens for users, roles, and tenant configuration.
- Add Playwright end-to-end tests in Week 4.
