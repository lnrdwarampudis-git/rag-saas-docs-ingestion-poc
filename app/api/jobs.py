from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.rag.analytics import record_job_cancel_audit_event, record_job_retry_audit_event
from app.rag.jobs import (
    cancel_processing_job,
    get_processing_job,
    process_processing_job,
    retry_processing_job,
)
from app.schemas.documents import ProcessingJobStatus

router = APIRouter(prefix="/processing-jobs", tags=["processing-jobs"])


@router.get("/{job_id}", response_model=ProcessingJobStatus)
def get_job_status(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    job = get_processing_job(job_id, current_user)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return job


@router.post("/{job_id}/run", response_model=ProcessingJobStatus)
def run_job_once(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    job = get_processing_job(job_id, current_user)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    result = process_processing_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return result


@router.post("/{job_id}/retry", response_model=ProcessingJobStatus)
def retry_failed_job(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    job = get_processing_job(job_id, current_user)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed processing jobs can be retried")
    result = retry_processing_job(job_id, current_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    record_job_retry_audit_event(current_user=current_user, job_status=result)
    return result


@router.post("/{job_id}/cancel", response_model=ProcessingJobStatus)
def cancel_job(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    job = get_processing_job(job_id, current_user)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    if job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only queued or processing jobs can be cancelled")
    result = cancel_processing_job(job_id, current_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    record_job_cancel_audit_event(current_user=current_user, job_status=result)
    return result
