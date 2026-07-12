# Week 5 Target Plan

## Goal

Close the biggest gap called out in every prior week's "Production Follow-Ups": replace client-supplied `tenant_id`/`role_names` with real authentication and server-resolved authorization, and give the POC an actual session model.

## Delivered In This Scaffold

1. Authentication (Keycloak OIDC)
   - `rag` realm auto-imported on `docker compose up` (`infra/keycloak/realm-export.json`)
   - Public SPA client (`rag-frontend`) using Authorization Code + PKCE; bearer-only API client (`rag-api`)
   - Demo users seeded one per role: `admin-demo`, `finance-demo`, `engineer-demo`, `legal-demo`, `support-demo` (password `Passw0rd!`)

2. JWT Validation Middleware
   - `app/auth/jwks.py` / `app/auth/tokens.py`: cached JWKS lookup, RS256 signature/issuer/audience/expiry validation on every request
   - `app/auth/dependencies.py`: `get_current_user` (401 on missing/invalid token) and `require_roles(...)` (403 on missing role)

3. Authorization (RBAC)
   - `app/auth/service.py` resolves tenant + roles from Postgres (`app_users` / `roles` / `user_roles`) by `keycloak_subject`, with a token-claims fallback if the database is unreachable
   - `tenant_id` and role names removed from `IngestRequest` / `QueryRequest` bodies entirely -- they can only come from the validated token
   - Fixed `private` visibility, which previously behaved like `tenant` visibility; it is now owner-scoped

4. Session Management
   - Stateless JWTs -- no server-side session store
   - Frontend (`frontend/src/auth/AuthProvider.tsx`) holds tokens in `sessionStorage`, silently refreshes ~30s before expiry via Keycloak's refresh-token grant, and clears state on logout or refresh failure
   - Manual tenant ID / "current member roles" inputs removed from the UI; identity now comes from the signed-in session

## Week 5 Exit Criteria

- `docker compose up -d --build` imports the `rag` realm and seeds matching Postgres RBAC rows.
- Signing in as any demo user resolves the correct tenant and roles via `GET /api/v1/auth/me`.
- `/api/v1/documents/*` and `/api/v1/query` reject requests without a valid bearer token (401).
- A user's own `tenant_id`/roles -- not request-body values -- determine what they can ingest and retrieve; cross-tenant and cross-role leakage is covered by API E2E tests.
- Backend unit + API E2E tests pass (`python3 -m pytest`); frontend type-check and production build pass (`npx tsc -b && npm run build`).

## Production Follow-Ups

- Add a server-side token revocation/blacklist (e.g. in Redis) if a move away from purely stateless JWTs is ever needed -- current design accepts that a stolen access token remains valid until it expires.
- Add admin UI/API for managing tenants, roles, and user-role assignments instead of editing `infra/postgres/init.sql` by hand.
- Tighten `role`-visibility documents so only roles the uploader themselves holds can be granted, instead of any role name.
- Add an audit log entry for logins/token refresh, not just document ingestion.
