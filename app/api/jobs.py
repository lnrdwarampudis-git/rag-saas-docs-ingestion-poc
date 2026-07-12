from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.rag.jobs import get_processing_job, process_processing_job
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
