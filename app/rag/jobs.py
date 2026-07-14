from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
import logging

from app.auth.models import AuthenticatedUser
from app.config import get_settings
from app.rag.ingestion import process_document_path
from app.rag.persistence import (
    get_persisted_processing_job,
    persist_processing_job_created,
    persist_processing_job_update,
)
from app.rag.store import document_store
from app.schemas.documents import ProcessingJobStatus

logger = logging.getLogger(__name__)

@dataclass
class ProcessingJob:
    job_id: UUID
    document_id: UUID
    tenant_id: UUID
    path: Path
    file_name: str
    visibility: str
    allowed_role_names: list[str]
    force_ocr: bool
    uploaded_by: str
    uploaded_by_user_id: UUID | None
    status: str = "queued"
    stage: str = "upload"
    attempts: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_status(self) -> ProcessingJobStatus:
        return ProcessingJobStatus(
            job_id=self.job_id,
            document_id=self.document_id,
            file_name=self.file_name,
            status=self.status,
            stage=self.stage,
            attempts=self.attempts,
            error_message=self.error_message,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            retry_history=list(_job_events.get(self.job_id, [])),
        )


_jobs: dict[UUID, ProcessingJob] = {}
_job_events: dict[UUID, list[str]] = {}


def create_processing_job(
    *,
    path: Path,
    file_name: str,
    tenant_id: UUID,
    uploaded_by: str,
    uploaded_by_user_id: UUID | None,
    visibility: str,
    allowed_role_names: list[str],
    force_ocr: bool,
) -> ProcessingJob:
    now = _utcnow()
    job = ProcessingJob(
        job_id=uuid4(),
        document_id=uuid4(),
        tenant_id=tenant_id,
        path=path,
        file_name=file_name,
        visibility=visibility,
        allowed_role_names=allowed_role_names,
        force_ocr=force_ocr,
        uploaded_by=uploaded_by,
        uploaded_by_user_id=uploaded_by_user_id,
        created_at=now,
    )
    _jobs[job.job_id] = job
    _record_job_event(job.job_id, "created")
    document_store.put_chunks(
        job.document_id,
        [],
        tenant_id=tenant_id,
        file_name=file_name,
        status="pending",
        visibility=visibility,
        allowed_role_names=allowed_role_names,
        ocr_used=False,
        byte_size=path.stat().st_size,
        mime_type=None,
        uploaded_by=uploaded_by,
    )
    persist_processing_job_created(job)
    return job


def enqueue_processing_job(job_id: UUID) -> None:
    queue_name = _queue_name_for_job(job_id)
    redis_client = _redis_client()
    if redis_client is None:
        logger.info(
            "Redis unavailable; processing job %s can be run by direct worker polling",
            job_id,
        )
        return
    try:
        redis_client.rpush(queue_name, str(job_id))
        logger.info("Enqueued processing job %s on %s", job_id, queue_name)
    except Exception:
        logger.exception("Failed to enqueue processing job %s in Redis queue %s", job_id, queue_name)


def get_processing_job(job_id: UUID, current_user: AuthenticatedUser) -> ProcessingJobStatus | None:
    job = _load_job(job_id)
    if job is None or job.tenant_id != current_user.tenant_id:
        return None
    return job.to_status()


def retry_processing_job(job_id: UUID, current_user: AuthenticatedUser) -> ProcessingJobStatus | None:
    job = _load_job(job_id)
    if job is None or job.tenant_id != current_user.tenant_id:
        return None
    if job.status != "failed":
        return job.to_status()

    job.status = "queued"
    job.stage = "upload"
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    _jobs[job.job_id] = job
    _record_job_event(job.job_id, f"retry:{job.attempts}")
    persist_processing_job_update(job)
    enqueue_processing_job(job.job_id)
    return job.to_status()


def cancel_processing_job(job_id: UUID, current_user: AuthenticatedUser) -> ProcessingJobStatus | None:
    job = _load_job(job_id)
    if job is None or job.tenant_id != current_user.tenant_id:
        return None
    if job.status in {"completed", "failed", "cancelled"}:
        return job.to_status()

    job.status = "cancelled"
    job.stage = "upload"
    job.error_message = "Cancelled by user"
    job.finished_at = _utcnow()
    _jobs[job.job_id] = job
    _record_job_event(job.job_id, "cancelled")
    persist_processing_job_update(job)
    return job.to_status()


def process_processing_job(job_id: UUID) -> ProcessingJobStatus | None:
    job = _load_job(job_id)
    if job is None:
        return None
    if job.status == "cancelled":
        return job.to_status()

    job.status = "processing"
    job.stage = "extract"
    job.attempts += 1
    job.started_at = job.started_at or _utcnow()
    job.error_message = None
    _jobs[job.job_id] = job
    persist_processing_job_update(job)

    try:
        job.stage = "chunk"
        persist_processing_job_update(job)
        result = process_document_path(
            path=job.path,
            tenant_id=job.tenant_id,
            uploaded_by=job.uploaded_by,
            uploaded_by_user_id=job.uploaded_by_user_id,
            visibility=job.visibility,
            allowed_role_names=job.allowed_role_names,
            force_ocr=job.force_ocr,
            file_name=job.file_name,
            document_id=job.document_id,
        )
        job.status = "completed" if result.chunks_created else "failed"
        job.stage = "embed"
        job.finished_at = _utcnow()
        if not result.chunks_created:
            job.error_message = "Document produced no chunks"
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.finished_at = _utcnow()
        logger.exception("Processing job %s failed", job.job_id)

    _jobs[job.job_id] = job
    persist_processing_job_update(job)
    if job.status == "failed" and job.attempts >= max(1, get_settings().processing_job_max_attempts):
        _dead_letter_processing_job(job)
    return job.to_status()


def process_next_queued_job(
    timeout_seconds: int = 5,
    queue_names: list[str] | None = None,
) -> ProcessingJobStatus | None:
    queues = queue_names or _worker_queue_names()
    redis_client = _redis_client()
    if redis_client is None:
        queued = sorted(
            (
                job
                for job in _jobs.values()
                if job.status == "queued" and _queue_name(job) in queues
            ),
            key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc),
        )
        return process_processing_job(queued[0].job_id) if queued else None

    try:
        item = redis_client.blpop(queues, timeout=timeout_seconds)
    except Exception as exc:
        if exc.__class__.__name__ == "TimeoutError":
            return None
        logger.exception("Failed to poll Redis processing queue")
        return None
    if item is None:
        return None
    _, raw_job_id = item
    return process_processing_job(UUID(raw_job_id))


def _dead_letter_processing_job(job: ProcessingJob) -> None:
    _record_job_event(job.job_id, "dead-lettered")
    redis_client = _redis_client()
    if redis_client is None:
        return
    try:
        redis_client.rpush(get_settings().processing_dead_letter_queue_name, str(job.job_id))
    except Exception:
        logger.exception("Failed to push processing job %s to dead-letter queue", job.job_id)


def _record_job_event(job_id: UUID, event: str) -> None:
    events = _job_events.setdefault(job_id, [])
    events.append(f"{_utcnow().isoformat()} {event}")


def _queue_name_for_job(job_id: UUID) -> str:
    job = _load_job(job_id)
    if job is None:
        return get_settings().processing_queue_name
    return _queue_name(job)


def _queue_name(job: ProcessingJob) -> str:
    settings = get_settings()
    return settings.ocr_processing_queue_name if job.force_ocr else settings.processing_queue_name


def _worker_queue_names() -> list[str]:
    settings = get_settings()
    queues = [
        queue.strip()
        for queue in settings.worker_queue_names.split(",")
        if queue.strip()
    ]
    return queues or [settings.processing_queue_name]


def _redis_client():
    try:
        from redis import Redis

        return Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_job(job_id: UUID) -> ProcessingJob | None:
    if get_settings().enable_db_persistence:
        persisted = get_persisted_processing_job(job_id)
        if persisted is not None:
            _jobs[job_id] = persisted
            return persisted
    return _jobs.get(job_id)
