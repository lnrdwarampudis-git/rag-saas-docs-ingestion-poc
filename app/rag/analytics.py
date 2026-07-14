from collections import deque
from dataclasses import dataclass
import hashlib
import json
from statistics import mean

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
    JobAnalytics,
    QueryAnalytics,
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


def record_query_event(
    *,
    tenant_id: str,
    cached: bool,
    retrieval_ms: float | int | None,
    total_ms: float | int | None,
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

    return _query_analytics_from_events(
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
    return EvaluationAnalytics(
        cases=summary["cases"],
        passed=summary["passed"],
        failed=summary["failed"],
        context_precision=summary["context_precision"],
        context_recall=summary["context_recall"],
        answer_relevance=summary["answer_relevance"],
        answer_groundedness=summary["answer_groundedness"],
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]
