from collections import deque
from dataclasses import dataclass
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


def get_analytics(current_user: AuthenticatedUser) -> AnalyticsResponse:
    documents, jobs = _persistent_operational_analytics(current_user)
    if documents is None:
        documents = _in_memory_document_analytics(current_user)
    if jobs is None:
        jobs = JobAnalytics()

    return AnalyticsResponse(
        documents=documents,
        jobs=jobs,
        queries=(
            _persistent_query_analytics(current_user)
            or _query_analytics(str(current_user.tenant_id))
        ),
        evaluation=_evaluation_analytics(),
        recent_events=_persistent_audit_events(current_user),
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
                      count(*) FILTER (WHERE status = 'failed') AS failed
                    FROM processing_jobs
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
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
            row = connection.execute(
                text(
                    """
                    WITH recent_events AS (
                      SELECT cached, retrieval_ms, total_ms
                      FROM query_events
                      WHERE tenant_id = :tenant_id
                      ORDER BY created_at DESC
                      LIMIT 500
                    )
                    SELECT
                      count(*) AS total,
                      count(*) FILTER (WHERE cached) AS cache_hits,
                      COALESCE(avg(retrieval_ms), 0) AS average_retrieval_ms,
                      COALESCE(avg(total_ms), 0) AS average_total_ms
                    FROM recent_events
                    """
                ),
                {"tenant_id": str(current_user.tenant_id)},
            ).mappings().one()
    except SQLAlchemyError:
        return None

    total = int(row["total"] or 0)
    if total == 0:
        return QueryAnalytics()

    cache_hits = int(row["cache_hits"] or 0)
    return QueryAnalytics(
        total=total,
        cache_hits=cache_hits,
        cache_misses=total - cache_hits,
        cache_hit_rate=round(cache_hits / total, 4),
        average_retrieval_ms=round(float(row["average_retrieval_ms"] or 0), 3),
        average_total_ms=round(float(row["average_total_ms"] or 0), 3),
    )


def _persistent_audit_events(
    current_user: AuthenticatedUser,
    limit: int = 8,
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
                    ORDER BY a.created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "tenant_id": str(current_user.tenant_id),
                    "limit": max(1, min(limit, 25)),
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
    if not events:
        return QueryAnalytics()
    cache_hits = sum(event.cached for event in events)
    total = len(events)
    return QueryAnalytics(
        total=total,
        cache_hits=cache_hits,
        cache_misses=total - cache_hits,
        cache_hit_rate=round(cache_hits / total, 4),
        average_retrieval_ms=round(mean(event.retrieval_ms for event in events), 3),
        average_total_ms=round(mean(event.total_ms for event in events), 3),
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
    )
