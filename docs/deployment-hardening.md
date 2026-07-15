# Deployment Hardening

This guide captures the production-readiness controls added after the local POC milestones. It is intentionally conservative: keep the local `docker-compose.yml` for development, and layer production-specific values through environment files, deployment overrides, and CI quality gates.

## Environment Strategy

Use [infra/deploy/.env.prod.example](../infra/deploy/.env.prod.example) as the production checklist. Copy it outside source control, replace every `change-me` value, and inject secrets through the target platform whenever possible.

Required secret classes:

- Postgres password
- MinIO root password
- Keycloak admin password
- External TLS/proxy certificates
- Optional Hugging Face token for gated local model weights

Keep public token-based LLM providers disabled unless explicitly approved:

```text
PUBLIC_LLM_ENABLED=false
LLM_PROVIDER=local
EMBEDDING_PROVIDER=local
```

## Compose Production Overlay

The production example overlay is [infra/deploy/docker-compose.prod.example.yml](../infra/deploy/docker-compose.prod.example.yml). It removes direct database/cache/object-store/vector-store host ports, enables restart policies, and keeps only the frontend exposed by default.

Validate locally:

```bash
docker compose -f docker-compose.yml -f infra/deploy/docker-compose.prod.example.yml config
```

## Kubernetes Starter

The Kubernetes starter manifest is [infra/k8s/rag-saas.example.yaml](../infra/k8s/rag-saas.example.yaml). It includes:

- namespace
- secret placeholders
- shared ConfigMap
- backend deployment and service
- worker deployment
- frontend deployment and LoadBalancer service

It expects managed or separately deployed Postgres, Redis, MinIO, Qdrant, and Keycloak endpoints to match the ConfigMap values. Replace image names, secrets, issuer URLs, and storage/networking before use.

## VM/Systemd Starter

The VM starter files in [infra/systemd](../infra/systemd) provide a non-Kubernetes deployment target for a hardened Linux host:

- `rag.env.example`: environment contract for backend and worker processes.
- `rag-backend.service.example`: FastAPI service running through Uvicorn.
- `rag-worker.service.example`: ingestion worker service for Redis-backed processing.
- `rag-ops-retention.service.example` and `rag-ops-retention.timer.example`: daily cleanup of persisted operations history.

Install the repository under `/opt/rag-saas-docs-ingestion-poc`, create a Python virtual environment, copy `rag.env.example` to `/etc/rag-saas/rag.env`, replace every placeholder, and point the service files at the installed path. Put TLS, static frontend hosting, and request limits in a reverse proxy such as Nginx or an equivalent load balancer.

After installation:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rag-backend rag-worker rag-ops-retention.timer
curl http://127.0.0.1:8000/health
```

## Render Starter

The Render starter blueprint is [infra/render/render.yaml.example](../infra/render/render.yaml.example). It defines:

- backend web service
- ingestion worker
- daily operations-history retention cron

It assumes managed or separately provisioned Postgres, Redis, MinIO-compatible object storage, Qdrant, and Keycloak/OIDC endpoints. Replace all `sync: false` values in Render with environment-specific secrets and URLs before deploying.

## Fly.io Starter

The Fly.io starter files in [infra/fly](../infra/fly) provide a Docker-based app and worker process layout:

- `fly.toml.example`: backend web process and ingestion worker process groups.
- `.env.fly.example`: secret/environment values to set with `fly secrets set`.

It assumes managed or separately provisioned Postgres, Redis, MinIO-compatible object storage, Qdrant, and Keycloak/OIDC endpoints. Copy the example to `fly.toml`, replace the `app` name and region, set secrets, and deploy:

```bash
cp infra/fly/fly.toml.example fly.toml
fly secrets import < infra/fly/.env.fly.example
fly deploy --config fly.toml
fly scale count app=1 worker=1
```

Run retained operations-history cleanup as a one-off Fly machine command or from an external scheduler:

```bash
fly ssh console -C "python -m app.rag.cleanup_ops_history --dry-run"
fly ssh console -C "python -m app.rag.cleanup_ops_history"
```

## ECS Starter

The ECS/Fargate starter files in [infra/ecs](../infra/ecs) provide AWS deployment manifests for:

- backend task definition and service behind an Application Load Balancer target group
- worker task definition and service
- one-shot operations-history retention task definition
- EventBridge rule target example for daily retention cleanup

The examples assume managed or separately provisioned Postgres, Redis, MinIO-compatible object storage, Qdrant, and Keycloak/OIDC endpoints. Replace the account, region, ECR image, IAM role, VPC subnet, security group, target group, and Secrets Manager placeholders before use.

Example flow:

```bash
aws ecs register-task-definition \
  --cli-input-json file://infra/ecs/backend-task-definition.example.json
aws ecs register-task-definition \
  --cli-input-json file://infra/ecs/worker-task-definition.example.json
aws ecs create-service \
  --cli-input-json file://infra/ecs/backend-service.example.json
aws ecs create-service \
  --cli-input-json file://infra/ecs/worker-service.example.json
```

Start with the overlay after preparing a real environment file:

```bash
docker compose --env-file /secure/path/rag-prod.env \
  -f docker-compose.yml \
  -f infra/deploy/docker-compose.prod.example.yml \
  up -d --build
```

## Backup Checklist

Run backups before upgrades, model-profile changes that require reindexing, and any storage maintenance.

Postgres:

```bash
docker compose exec postgres pg_dump -U rag -d rag -Fc > backups/rag-$(date +%Y%m%d-%H%M%S).dump
```

MinIO:

```bash
mc alias set rag-minio http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mirror rag-minio/rag-upload-sessions backups/minio/rag-upload-sessions
```

Qdrant:

```bash
curl -X POST http://localhost:6333/collections/rag_chunks/snapshots
curl http://localhost:6333/collections/rag_chunks/snapshots
```

Redis queue/cache snapshot:

```bash
docker compose exec redis redis-cli BGSAVE
docker cp "$(docker compose ps -q redis)":/data/dump.rdb backups/redis-dump.rdb
```

## Restore Checklist

Restore into an empty environment first, then run vector checks before opening traffic.

Postgres:

```bash
cat backups/rag.dump | docker compose exec -T postgres pg_restore -U rag -d rag --clean --if-exists
```

MinIO:

```bash
mc mirror backups/minio/rag-upload-sessions rag-minio/rag-upload-sessions
```

Qdrant:

```bash
curl -X PUT http://localhost:6333/collections/rag_chunks/snapshots/recover \
  -H "content-type: application/json" \
  -d '{"location":"file:///qdrant/snapshots/rag_chunks.snapshot"}'
```

Redis:

Stop Redis, replace `/data/dump.rdb`, then restart Redis. For production, prefer draining processing queues before Redis restore unless the target recovery point intentionally includes queued jobs.

After restore:

```bash
docker compose exec backend python -m app.rag.vector_ops
docker compose exec backend python -m app.eval.run
curl http://127.0.0.1:8000/health
```

## CI Quality Gates

The GitHub Actions workflow in [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs:

- `python -m ruff check app tests`
- `python -m pytest`
- `python -m app.eval.run`
- `npm run build`
- `docker compose config`
- production overlay Compose config validation
- `git diff --check`

Keep those same checks green before applying patches or deploying.

## Operations Gates

Before production traffic:

1. Confirm `/api/v1/model-status` shows ready runtimes.
2. Run `python -m app.rag.vector_ops` after changing vector backend or embedding model.
3. Confirm `/api/v1/analytics` shows normal retrieval status and no unexpected dead-letter backlog.
4. Confirm the retrieval evaluation gate has zero failed cases.
5. Confirm backups exist for Postgres, MinIO, Qdrant, and Redis.

## Durable Operations Tables

The app now records durable operational history when `ENABLE_DB_PERSISTENCE=true`:

- `processing_job_events`: created/retry/cancel/dead-letter job lifecycle events.
- `model_latency_events`: model/vector/reranker latency buckets by query runtime shape.
- `evaluation_runs`: persisted retrieval quality-gate reports for trend history.

The Admin Analytics API rolls these into recent job events, model latency buckets, and evaluation trend points. The Admin Analytics UI now includes detail tables for model-latency buckets, persisted evaluation trends, processing job events, and Qdrant diagnostics.

Run cleanup manually or through cron/timers:

```bash
python -m app.rag.cleanup_ops_history --dry-run
python -m app.rag.cleanup_ops_history
```

Default retention windows are:

- `QUERY_EVENTS_RETENTION_DAYS=30`
- `MODEL_LATENCY_EVENTS_RETENTION_DAYS=30`
- `PROCESSING_JOB_EVENTS_RETENTION_DAYS=30`
- `EVALUATION_RUNS_RETENTION_DAYS=90`

## Qdrant Diagnostics

When `VECTOR_INDEX_BACKEND=qdrant`, `/api/v1/analytics` checks the live collection, vector counts, segment count, optimizer status, and payload-index coverage for RBAC filter fields. Missing payload indexes or non-green optimizer status are surfaced as attention states in the Admin Analytics UI. Run the vector ops command after backend, embedding, or Qdrant changes:

```bash
python -m app.rag.vector_ops
```
