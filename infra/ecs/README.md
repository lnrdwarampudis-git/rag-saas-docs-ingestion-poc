# ECS Starter

These files are starter manifests for running the app on AWS ECS/Fargate. They assume managed or separately provisioned dependencies for Postgres, Redis, MinIO-compatible object storage, Qdrant, and Keycloak/OIDC.

Replace every placeholder before use:

- AWS account, region, task execution role, and task role ARNs.
- Container image URI in ECR or another registry reachable by ECS.
- VPC subnets, security groups, target group ARN, and cluster name.
- Secrets Manager or SSM Parameter Store ARNs for database, Redis, object storage, Qdrant, and OIDC values.

Example registration flow:

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

Run the retained operations-history cleanup through EventBridge Scheduler or an equivalent cron runner:

```bash
aws ecs register-task-definition \
  --cli-input-json file://infra/ecs/ops-retention-task-definition.example.json
```
