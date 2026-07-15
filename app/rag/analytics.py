from collections import deque
from dataclasses import dataclass
import hashlib
import json
from statistics import mean

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import AuthenticatedUser
from app.config import get_settings
from app.eval.run import run_eval
from app.rag.store import document_store
from app.schemas.analytics import (
    AnalyticsResponse,
    AuditEvent,
    DocumentAnalytics,
    EvaluationAnalytics,
    EvaluationTrendPoint,
    JobAnalytics,
    ModelLatencyBucket,
    QueryAnalytics,
    QdrantAnalytics,
    RetrievalAnalytics,
)


@dataclass(frozen=True)
class QueryEvent:
    tenant_id: str
    cached: bool
    retrieval_ms: float
    total_ms: float


_query_events: deque[QueryEvent] = deque(maxlen=500)
_query_events_table_ready = False
_model_latency_events_table_ready = False
_processing_job_events_table_ready = False
_evaluation_runs_table_ready = False


def record_query_event(
    *,
    tenant_id: str,
    cached: bool,
    retrieval_ms: float | int | None,
    total_ms: float | int | None,
    metrics: dict | None = None,
) -> None:
    _query_events.append(
        QueryEvent(
            tenant_id=tenant_id,
            cached=cached,
            retrieval_ms=float(retrieval_ms or 0),
            total_ms=float(total_ms or 0),
        )
    )
    _record_persistent_query_event(
        tenant_id=tenant_id,
        cached=cached,
        retrieval_ms=float(retrieval_ms or 0),
        total_ms=float(total_ms or 0),
    )
    _record_persistent_model_latency_event(
        tenant_id=tenant_id,
        cached=cached,
        retrieval_ms=float(retrieval_ms or 0),
        total_ms=float(total_ms or 0),
        metrics=metrics or {},
    )


def record_query_audit_event(
    *,
    current_user: AuthenticatedUser,
    query: str,
    top_k: int,
    cached: bool,
    citations: list[dict],
    metrics: dict,
) -> None:
    if not get_settings().enable_db_persistence:
        return

    metadata = {
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "query_length": len(query),
        "top_k": top_k,
        "cached": cached,
        "contexts_used": int(metrics.get("contexts_used") or 0),
        "retrieval_ms": float(metrics.get("retrieval_ms") or 0),
        "total_ms": float(metrics.get("total_ms") or 0),
        "embedding_model": metrics.get("embedding_model"),
        "answer_model": metrics.get("answer_model"),
        "citation_document_ids": _citation_document_ids(citations),
    }

    try:
        from app.db import engine

        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    INSERT INTO audit_logs (
                      tenant_id, actor_user_id, action, resource_type, metadata
                    )
                    VALUES (
                      :tenant_id, :actor_user_id, 'query.executed', 'query',
                      {_metadata_sql_expression(connection)}
                    )
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "actor_user_id": (
                        str(current_user.app_user_id) if current_user.app_user_id else None
                    ),
                    "metadata": json.dumps(metadata),
                },
            )
    except SQLAlchemyError:
        return


def record_job_retry_audit_event(
    *,
    current_user: AuthenticatedUser,
    job_status,
) -> None:
    if not get_settings().enable_db_persistence:
        return

    metadata = {
        "job_id": str(job_status.job_id),
        "document_id": str(job_status.document_id),
        "file_name": job_status.file_name,
        "attempts": job_status.attempts,
        "status": job_status.status,
        "stage": job_status.stage,
    }

    try:
        from app.db import engine

        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    INSERT INTO audit_logs (
                      tenant_id, actor_user_id, action, resource_type, resource_id, metadata
                    )
                    VALUES (
                      :tenant_id, :actor_user_id, 'processing_job.retried',
                      'processing_job', :resource_id, {_metadata_sql_expression(connection)}
                    )
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "actor_user_id": (
                        str(current_user.app_user_id) if current_user.app_user_id else None
                    ),
                    "resource_id": str(job_status.job_id),
                    "metadata": json.dumps(metadata),
                },
            )
    except SQLAlchemyError:
        return


def record_job_cancel_audit_event(
    *,
    current_user: AuthenticatedUser,
    job_status,
) -> None:
    _record_processing_job_audit_event(
        current_user=current_user,
        job_status=job_status,
        action="processing_job.cancelled",
    )


def record_processing_job_event(
    *,
    tenant_id,
    job_id,
    document_id,
    event: str,
    status: str,
    attempts: int,
    metadata: dict | None = None,
) -> None:
    if not get_settings().enable_db_persistence:
        return
    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_processing_job_events_table(connection)
            connection.execute(
                text(
                    f"""
                    INSERT INTO processing_job_events (
                      tenant_id, job_id, document_id, event, status, attempts, metadata
                    )
                    VALUES (
                      :tenant_id, :job_id, :document_id, :event, :status, :attempts,
                      {_metadata_sql_expression(connection)}
                    )
                    """
                ),
                {
                    "tenant_id": str(tenant_id),
                    "job_id": str(job_id),
                    "document_id": str(document_id),
                    "event": event,
                    "status": status,
                    "attempts": attempts,
                    "metadata": json.dumps(metadata or {}),
                },
            )
    except SQLAlchemyError:
        return


def _record_processing_job_audit_event(
    *,
    current_user: AuthenticatedUser,
    job_status,
    action: str,
) -> None:
    if not get_settings().enable_db_persistence:
        return

    metadata = {
        "job_id": str(job_status.job_id),
        "document_id": str(job_status.document_id),
        "file_name": job_status.file_name,
        "attempts": job_status.attempts,
        "status": job_status.status,
        "stage": job_status.stage,
    }

    try:
        from app.db import engine

        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    INSERT INTO audit_logs (
                      tenant_id, actor_user_id, action, resource_type, resource_id, metadata
                    )
                    VALUES (
                      :tenant_id, :actor_user_id, :action, 'processing_job',
                      :resource_id, {_metadata_sql_expression(connection)}
                    )
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "actor_user_id": (
                        str(current_user.app_user_id) if current_user.app_user_id else None
                    ),
                    "action": action,
                    "resource_id": str(job_status.job_id),
                    "metadata": json.dumps(metadata),
                },
            )
    except SQLAlchemyError:
        return


def get_analytics(
    current_user: AuthenticatedUser,
    *,
    audit_action: str | None = None,
    audit_resource_type: str | None = None,
) -> AnalyticsResponse:
    documents, jobs = _persistent_operational_analytics(current_user)
    if documents is None:
        documents = _in_memory_document_analytics(current_user)
    if jobs is None:
        jobs = JobAnalytics()

    queries = _persistent_query_analytics(current_user) or _query_analytics(str(current_user.tenant_id))
    return AnalyticsResponse(
        documents=documents,
        jobs=jobs,
        queries=queries,
        retrieval=_retrieval_analytics(queries),
        evaluation=_evaluation_analytics(),
        recent_events=_persistent_audit_events(
            current_user,
            action=audit_action,
            resource_type=audit_resource_type,
        ),
    )


def _record_persistent_query_event(
    *,
    tenant_id: str,
    cached: bool,
    retrieval_ms: float,
    total_ms: float,
) -> None:
    if not get_settings().enable_db_persistence:
        return

    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_query_events_table(connection)
            connection.execute(
                text(
                    """
                    INSERT INTO query_events (tenant_id, cached, retrieval_ms, total_ms)
                    VALUES (:tenant_id, :cached, :retrieval_ms, :total_ms)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "cached": cached,
                    "retrieval_ms": retrieval_ms,
                    "total_ms": total_ms,
                },
            )
    except SQLAlchemyError:
        return


def _record_persistent_model_latency_event(
    *,
    tenant_id: str,
    cached: bool,
    retrieval_ms: float,
    total_ms: float,
    metrics: dict,
) -> None:
    if not get_settings().enable_db_persistence:
        return
    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_model_latency_events_table(connection)
            connection.execute(
                text(
                    """
                    INSERT INTO model_latency_events (
                      tenant_id, cached, retrieval_ms, total_ms, embedding_model,
                      answer_model, vector_index_backend, reranker_runtime
                    )
                    VALUES (
                      :tenant_id, :cached, :retrieval_ms, :total_ms, :embedding_model,
                      :answer_model, :vector_index_backend, :reranker_runtime
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "cached": cached,
                    "retrieval_ms": retrieval_ms,
                    "total_ms": total_ms,
                    "embedding_model": metrics.get("embedding_model"),
                    "answer_model": metrics.get("answer_model"),
                    "vector_index_backend": metrics.get("vector_index_backend"),
                    "reranker_runtime": metrics.get("local_reranker_runtime"),
                },
            )
    except SQLAlchemyError:
        return


def _persistent_operational_analytics(
    current_user: AuthenticatedUser,
) -> tuple[DocumentAnalytics | None, JobAnalytics | None]:
    if not get_settings().enable_db_persistence:
        return None, None

    try:
        from app.db import engine

        with engine.begin() as connection:
            document_row = connection.execute(
                text(
                    """
                    SELECT
                      count(*) AS total,
                      count(*) FILTER (WHERE status = 'embedded') AS embedded,
                      count(*) FILTER (WHERE status IN ('pending', 'extracting', 'chunking')) AS pending,
                      count(*) FILTER (WHERE status = 'failed') AS failed,
                      COALESCE(sum(chunk_count), 0) AS chunks,
                      count(*) FILTER (WHERE ocr_used) AS ocr_documents
                    FROM (
                      SELECT
                        d.id,
                        d.status::text AS status,
                        count(c.id) AS chunk_count,
                        bool_or(c.ocr_used) AS ocr_used
                      FROM documents d
                      LEFT JOIN document_chunks c ON c.document_id = d.id
                      WHERE d.tenant_id = :tenant_id
                      GROUP BY d.id
                    ) document_rollup
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
            ).mappings().one()
            job_row = connection.execute(
                text(
                    """
                    SELECT
                      count(*) AS total,
                      count(*) FILTER (WHERE status = 'queued') AS queued,
                      count(*) FILTER (WHERE status = 'processing') AS processing,
                      count(*) FILTER (WHERE status = 'completed') AS completed,
                      count(*) FILTER (WHERE status = 'failed') AS failed,
                      count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
                      count(*) FILTER (
                        WHERE status = 'failed' AND attempts >= :max_attempts
                      ) AS dead_lettered
                    FROM processing_jobs
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "max_attempts": max(1, get_settings().processing_job_max_attempts),
                },
            ).mappings().one()
            failure_rows = connection.execute(
                text(
                    """
                    SELECT d.file_name
                    FROM processing_jobs j
                    JOIN documents d ON d.id = j.document_id
                    WHERE j.tenant_id = :tenant_id AND j.status = 'failed'
                    ORDER BY COALESCE(j.finished_at, j.created_at) DESC
                    LIMIT 5
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
            ).mappings()
            recent_failures = [str(row["file_name"]) for row in failure_rows]
            _ensure_processing_job_events_table(connection)
            event_rows = connection.execute(
                text(
                    """
                    SELECT event, status, attempts, created_at
                    FROM processing_job_events
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                    LIMIT 8
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
            ).mappings()
            recent_events = [
                f"{_datetime_string(row['created_at'])} {row['event']} {row['status']} attempt={row['attempts']}"
                for row in event_rows
            ]

        return (
            DocumentAnalytics(
                total=int(document_row["total"] or 0),
                embedded=int(document_row["embedded"] or 0),
                pending=int(document_row["pending"] or 0),
                failed=int(document_row["failed"] or 0),
                chunks=int(document_row["chunks"] or 0),
                ocr_documents=int(document_row["ocr_documents"] or 0),
            ),
            JobAnalytics(
                total=int(job_row["total"] or 0),
                queued=int(job_row["queued"] or 0),
                processing=int(job_row["processing"] or 0),
                completed=int(job_row["completed"] or 0),
                failed=int(job_row["failed"] or 0),
                cancelled=int(job_row["cancelled"] or 0),
                dead_lettered=int(job_row["dead_lettered"] or 0),
                recent_failures=recent_failures,
                recent_events=recent_events,
            ),
        )
    except SQLAlchemyError:
        return None, None


def _persistent_query_analytics(current_user: AuthenticatedUser) -> QueryAnalytics | None:
    if not get_settings().enable_db_persistence:
        return None

    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_query_events_table(connection)
            rows = list(
                connection.execute(
                    text(
                        """
                        SELECT cached, retrieval_ms, total_ms
                        FROM query_events
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC
                        LIMIT 500
                        """
                    ),
                    {"tenant_id": str(current_user.tenant_id)},
                ).mappings()
            )
    except SQLAlchemyError:
        return None

    analytics = _query_analytics_from_events(
        [
            QueryEvent(
                tenant_id=str(current_user.tenant_id),
                cached=bool(row["cached"]),
                retrieval_ms=float(row["retrieval_ms"] or 0),
                total_ms=float(row["total_ms"] or 0),
            )
            for row in rows
        ]
    )
    analytics.model_latency_buckets = _persistent_model_latency_buckets(current_user)
    return analytics


def _persistent_model_latency_buckets(current_user: AuthenticatedUser) -> list[ModelLatencyBucket]:
    if not get_settings().enable_db_persistence:
        return []
    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_model_latency_events_table(connection)
            rows = connection.execute(
                text(
                    """
                    SELECT embedding_model, answer_model, vector_index_backend, reranker_runtime, total_ms
                    FROM model_latency_events
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                    LIMIT 500
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
            ).mappings()
    except SQLAlchemyError:
        return []

    buckets: dict[str, list[float]] = {}
    for row in rows:
        key = " / ".join(
            [
                str(row["embedding_model"] or "unknown-embedding"),
                str(row["answer_model"] or "unknown-answer"),
                str(row["vector_index_backend"] or "unknown-vector"),
                str(row["reranker_runtime"] or "none"),
            ]
        )
        buckets.setdefault(key, []).append(float(row["total_ms"] or 0))
    return [
        ModelLatencyBucket(
            model_key=key,
            total=len(values),
            average_total_ms=round(mean(values), 3),
            p95_total_ms=round(_percentile(values, 0.95), 3),
        )
        for key, values in sorted(buckets.items())
    ]


def _persistent_audit_events(
    current_user: AuthenticatedUser,
    limit: int = 8,
    action: str | None = None,
    resource_type: str | None = None,
) -> list[AuditEvent]:
    if not get_settings().enable_db_persistence:
        return []

    try:
        from app.db import engine

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                      a.action,
                      a.resource_type,
                      CAST(a.resource_id AS TEXT) AS resource_id,
                      a.metadata,
                      a.created_at,
                      COALESCE(u.display_name, u.email) AS actor
                    FROM audit_logs a
                    LEFT JOIN app_users u ON u.id = a.actor_user_id
                    WHERE a.tenant_id = :tenant_id
                      AND (:action IS NULL OR a.action = :action)
                      AND (:resource_type IS NULL OR a.resource_type = :resource_type)
                    ORDER BY a.created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "limit": max(1, min(limit, 25)),
                    "action": action,
                    "resource_type": resource_type,
                },
            ).mappings()
            return [
                AuditEvent(
                    action=str(row["action"]),
                    resource_type=str(row["resource_type"]),
                    resource_id=str(row["resource_id"]) if row["resource_id"] else None,
                    actor=str(row["actor"]) if row["actor"] else None,
                    metadata=_metadata_dict(row["metadata"]),
                    created_at=_datetime_string(row["created_at"]),
                )
                for row in rows
            ]
    except SQLAlchemyError:
        return []


def _ensure_query_events_table(connection: Connection) -> None:
    global _query_events_table_ready
    if _query_events_table_ready:
        return

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS query_events (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              cached BOOLEAN NOT NULL DEFAULT FALSE,
              retrieval_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
              total_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_query_events_tenant_time
            ON query_events (tenant_id, created_at DESC)
            """
        )
    )
    _query_events_table_ready = True


def _ensure_model_latency_events_table(connection: Connection) -> None:
    global _model_latency_events_table_ready
    if _model_latency_events_table_ready:
        return
    id_column = _id_column_sql(connection)
    created_at_column = _created_at_column_sql(connection)
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS model_latency_events (
              {id_column},
              tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              cached BOOLEAN NOT NULL DEFAULT FALSE,
              retrieval_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
              total_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
              embedding_model TEXT,
              answer_model TEXT,
              vector_index_backend TEXT,
              reranker_runtime TEXT,
              {created_at_column}
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_latency_events_tenant_time
            ON model_latency_events (tenant_id, created_at DESC)
            """
        )
    )
    _model_latency_events_table_ready = True


def _ensure_processing_job_events_table(connection: Connection) -> None:
    global _processing_job_events_table_ready
    if _processing_job_events_table_ready:
        return
    id_column = _id_column_sql(connection)
    created_at_column = _created_at_column_sql(connection)
    metadata_type = "JSONB" if connection.dialect.name == "postgresql" else "TEXT"
    metadata_default = "'{}'::JSONB" if connection.dialect.name == "postgresql" else "'{}'"
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS processing_job_events (
              {id_column},
              tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              job_id UUID NOT NULL,
              document_id UUID NOT NULL,
              event TEXT NOT NULL,
              status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              metadata {metadata_type} NOT NULL DEFAULT {metadata_default},
              {created_at_column}
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_processing_job_events_tenant_time
            ON processing_job_events (tenant_id, created_at DESC)
            """
        )
    )
    _processing_job_events_table_ready = True


def _in_memory_document_analytics(current_user: AuthenticatedUser) -> DocumentAnalytics:
    documents = [
        document
        for document in document_store.list_documents()
        if document.tenant_id == current_user.tenant_id
    ]
    return DocumentAnalytics(
        total=len(documents),
        embedded=sum(document.status == "embedded" for document in documents),
        pending=sum(document.status in {"pending", "extracting", "chunking"} for document in documents),
        failed=sum(document.status == "failed" for document in documents),
        chunks=sum(document.chunks_created for document in documents),
        ocr_documents=sum(document.ocr_used for document in documents),
    )


def _query_analytics(tenant_id: str) -> QueryAnalytics:
    events = [event for event in _query_events if event.tenant_id == tenant_id]
    return _query_analytics_from_events(events)


def _query_analytics_from_events(events: list[QueryEvent]) -> QueryAnalytics:
    if not events:
        return QueryAnalytics()
    cache_hits = sum(event.cached for event in events)
    total = len(events)
    retrieval_values = [event.retrieval_ms for event in events]
    total_values = [event.total_ms for event in events]
    recent_values = total_values[:25]
    return QueryAnalytics(
        total=total,
        cache_hits=cache_hits,
        cache_misses=total - cache_hits,
        cache_hit_rate=round(cache_hits / total, 4),
        average_retrieval_ms=round(mean(retrieval_values), 3),
        average_total_ms=round(mean(total_values), 3),
        p95_retrieval_ms=round(_percentile(retrieval_values, 0.95), 3),
        p95_total_ms=round(_percentile(total_values, 0.95), 3),
        recent_average_total_ms=round(mean(recent_values), 3),
    )


def _retrieval_analytics(queries: QueryAnalytics) -> RetrievalAnalytics:
    settings = get_settings()
    return RetrievalAnalytics(
        vector_index_backend=settings.vector_index_backend,
        reranker_runtime=settings.local_reranker_runtime,
        average_retrieval_ms=queries.average_retrieval_ms,
        p95_retrieval_ms=queries.p95_retrieval_ms,
        retrieval_warning_ms=settings.retrieval_latency_warning_ms,
        retrieval_attention=(
            queries.total > 0
            and (
                queries.average_retrieval_ms > settings.retrieval_latency_warning_ms
                or queries.p95_retrieval_ms > settings.retrieval_latency_warning_ms
            )
        ),
        qdrant=_qdrant_analytics(settings),
    )


def _qdrant_analytics(settings) -> QdrantAnalytics | None:
    if settings.vector_index_backend.lower() != "qdrant":
        return None
    from app.rag.vector_index import QdrantVectorIndex

    required_payload_indexes = sorted(QdrantVectorIndex.payload_indexes)
    try:
        with httpx.Client(
            base_url=settings.qdrant_url.rstrip("/"),
            timeout=min(settings.qdrant_request_timeout_seconds, 5.0),
        ) as client:
            response = client.get(f"/collections/{settings.qdrant_collection_name}")
    except httpx.HTTPError as exc:
        return QdrantAnalytics(
            ready=False,
            collection_name=settings.qdrant_collection_name,
            required_payload_indexes=required_payload_indexes,
            message=f"Qdrant is not reachable: {exc.__class__.__name__}",
        )
    if response.status_code != 200:
        return QdrantAnalytics(
            ready=False,
            collection_name=settings.qdrant_collection_name,
            required_payload_indexes=required_payload_indexes,
            message=f"Qdrant collection check returned HTTP {response.status_code}",
        )
    result = response.json().get("result", {})
    optimizer_status = result.get("optimizer_status")
    if isinstance(optimizer_status, dict):
        optimizer_status = optimizer_status.get("status") or json.dumps(optimizer_status)
    optimizer_status_text = str(optimizer_status or "unknown")
    payload_schema = result.get("payload_schema") or {}
    indexed_payload_fields = sorted(payload_schema) if isinstance(payload_schema, dict) else []
    missing_payload_indexes = [
        field_name for field_name in required_payload_indexes if field_name not in indexed_payload_fields
    ]
    optimizer_attention = optimizer_status_text.lower() not in {"ok", "green", "unknown"}
    index_attention = bool(missing_payload_indexes)
    message = "Qdrant collection health loaded."
    if missing_payload_indexes:
        message = f"Qdrant missing payload indexes: {', '.join(missing_payload_indexes)}"
    elif optimizer_attention:
        message = f"Qdrant optimizer status needs attention: {optimizer_status_text}"
    return QdrantAnalytics(
        ready=True,
        collection_name=settings.qdrant_collection_name,
        points_count=int(result.get("points_count") or 0),
        indexed_vectors_count=int(result.get("indexed_vectors_count") or 0),
        segments_count=int(result.get("segments_count") or 0),
        status=str(result.get("status") or "unknown"),
        optimizer_status=optimizer_status_text,
        indexed_payload_fields=indexed_payload_fields,
        required_payload_indexes=required_payload_indexes,
        missing_payload_indexes=missing_payload_indexes,
        optimizer_attention=optimizer_attention,
        index_attention=index_attention,
        message=message,
    )


def _metadata_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_sql_expression(connection: Connection) -> str:
    if connection.dialect.name == "postgresql":
        return "CAST(:metadata AS jsonb)"
    return ":metadata"


def _citation_document_ids(citations: list[dict]) -> list[str]:
    document_ids = []
    for citation in citations:
        document_id = citation.get("document_id")
        if document_id and str(document_id) not in document_ids:
            document_ids.append(str(document_id))
    return document_ids


def _datetime_string(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _evaluation_analytics() -> EvaluationAnalytics:
    summary = run_eval()["summary"]
    trend = _persistent_evaluation_trend()
    return EvaluationAnalytics(
        cases=summary["cases"],
        passed=summary["passed"],
        failed=summary["failed"],
        context_precision=summary["context_precision"],
        context_recall=summary["context_recall"],
        answer_relevance=summary["answer_relevance"],
        answer_groundedness=summary["answer_groundedness"],
        last_run_at=trend[0].created_at if trend else None,
        trend=trend,
    )


def _persistent_evaluation_trend() -> list[EvaluationTrendPoint]:
    if not get_settings().enable_db_persistence:
        return []
    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_evaluation_runs_table(connection)
            rows = connection.execute(
                text(
                    """
                    SELECT created_at, cases, failed, context_precision, answer_groundedness
                    FROM evaluation_runs
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                )
            ).mappings()
            return [
                EvaluationTrendPoint(
                    created_at=_datetime_string(row["created_at"]),
                    cases=int(row["cases"] or 0),
                    failed=int(row["failed"] or 0),
                    context_precision=float(row["context_precision"] or 0),
                    answer_groundedness=float(row["answer_groundedness"] or 0),
                )
                for row in rows
            ]
    except SQLAlchemyError:
        return []


def _ensure_evaluation_runs_table(connection: Connection) -> None:
    global _evaluation_runs_table_ready
    if _evaluation_runs_table_ready:
        return
    id_column = _id_column_sql(connection)
    created_at_column = _created_at_column_sql(connection)
    report_type = "JSONB" if connection.dialect.name == "postgresql" else "TEXT"
    report_default = "'{}'::JSONB" if connection.dialect.name == "postgresql" else "'{}'"
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
              {id_column},
              cases INTEGER NOT NULL,
              passed INTEGER NOT NULL,
              failed INTEGER NOT NULL,
              context_precision DOUBLE PRECISION NOT NULL DEFAULT 0,
              context_recall DOUBLE PRECISION NOT NULL DEFAULT 0,
              answer_relevance DOUBLE PRECISION NOT NULL DEFAULT 0,
              answer_groundedness DOUBLE PRECISION NOT NULL DEFAULT 0,
              report {report_type} NOT NULL DEFAULT {report_default},
              {created_at_column}
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at
            ON evaluation_runs (created_at DESC)
            """
        )
    )
    _evaluation_runs_table_ready = True


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _id_column_sql(connection: Connection) -> str:
    if connection.dialect.name == "postgresql":
        return "id UUID PRIMARY KEY DEFAULT gen_random_uuid()"
    return "id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16))))"


def _created_at_column_sql(connection: Connection) -> str:
    if connection.dialect.name == "postgresql":
        return "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    return "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
