from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.config import get_settings
from app.rag.persistence import get_persisted_document, list_persisted_documents
from app.rag.ingestion import process_document_path
from app.rag.jobs import create_processing_job, enqueue_processing_job
from app.rag.retrieval import is_chunk_authorized
from app.rag.store import document_store
from app.rag.upload_sessions import (
    assemble_upload_session,
    create_upload_session,
    get_upload_session,
    save_upload_part,
)
from app.schemas.documents import (
    ChunkDTO,
    DocumentDetail,
    DocumentIngestResult,
    DocumentListResponse,
    DocumentSummary,
    IngestRequest,
    ProcessingJobStatus,
    UploadSessionCreateRequest,
    UploadSessionStatus,
)

router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024

class DocumentChunksResponse(BaseModel):
    document_id: UUID
    chunks: list[ChunkDTO] = Field(default_factory=list)


def _upload_session_status(upload_session_id: UUID) -> UploadSessionStatus:
    session = get_upload_session(upload_session_id)
    return UploadSessionStatus(
        upload_session_id=session.upload_session_id,
        file_name=session.file_name,
        byte_size=session.byte_size,
        part_size_bytes=get_settings().upload_session_part_bytes,
        uploaded_parts=session.uploaded_parts,
        complete=False,
    )


def _require_upload_session_access(
    upload_session_id: UUID,
    current_user: AuthenticatedUser,
):
    session = get_upload_session(upload_session_id)
    if (
        session.tenant_id != current_user.tenant_id
        or session.uploaded_by != current_user.keycloak_subject
    ):
        raise HTTPException(status_code=404, detail="Upload session not found")
    return session


@router.get("", response_model=DocumentListResponse)
def list_documents(current_user: AuthenticatedUser = Depends(get_current_user)) -> DocumentListResponse:
    documents = list_persisted_documents(current_user)
    if not documents:
        documents = [
            document
            for document in document_store.list_documents()
            if _is_document_summary_authorized(document, current_user)
        ]
    return DocumentListResponse(documents=documents)


@router.post("/ingest", response_model=DocumentIngestResult)
def ingest_document(
    payload: IngestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentIngestResult:
    path = _resolve_ingest_path(payload.local_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {payload.local_path}")

    return process_document_path(
        path=path,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        uploaded_by_user_id=current_user.app_user_id,
        visibility=payload.visibility,
        allowed_role_names=payload.allowed_role_names,
        force_ocr=payload.force_ocr,
    )


@router.post("/upload", response_model=DocumentIngestResult)
def upload_document(
    visibility: str = Form("tenant"),
    allowed_role_names: list[str] = Form(default=[]),
    force_ocr: bool = Form(False),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentIngestResult:
    if visibility not in {"private", "tenant", "role"}:
        raise HTTPException(status_code=422, detail="visibility must be private, tenant, or role")
    if not file.filename:
        raise HTTPException(status_code=422, detail="Uploaded file must have a filename")

    path, original_file_name = _save_upload(file)
    return process_document_path(
        path=path,
        file_name=original_file_name,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        uploaded_by_user_id=current_user.app_user_id,
        visibility=visibility,
        allowed_role_names=allowed_role_names if visibility == "role" else [],
        force_ocr=force_ocr,
    )


@router.post("/upload-async", response_model=ProcessingJobStatus, status_code=202)
def upload_document_async(
    visibility: str = Form("tenant"),
    allowed_role_names: list[str] = Form(default=[]),
    force_ocr: bool = Form(False),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    if visibility not in {"private", "tenant", "role"}:
        raise HTTPException(status_code=422, detail="visibility must be private, tenant, or role")
    if not file.filename:
        raise HTTPException(status_code=422, detail="Uploaded file must have a filename")

    path, original_file_name = _save_upload(file)
    job = create_processing_job(
        path=path,
        file_name=original_file_name,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        uploaded_by_user_id=current_user.app_user_id,
        visibility=visibility,
        allowed_role_names=allowed_role_names if visibility == "role" else [],
        force_ocr=force_ocr,
    )
    enqueue_processing_job(job.job_id)
    return job.to_status()


@router.post("/upload-sessions", response_model=UploadSessionStatus, status_code=201)
def create_resumable_upload_session(
    payload: UploadSessionCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadSessionStatus:
    _validate_upload_extension(payload.file_name)
    session = create_upload_session(
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        file_name=payload.file_name,
        byte_size=payload.byte_size,
        visibility=payload.visibility,
        allowed_role_names=payload.allowed_role_names,
        force_ocr=payload.force_ocr,
    )
    return UploadSessionStatus(
        upload_session_id=session.upload_session_id,
        file_name=session.file_name,
        byte_size=session.byte_size,
        part_size_bytes=get_settings().upload_session_part_bytes,
        uploaded_parts=[],
        complete=False,
    )


@router.get("/upload-sessions/{upload_session_id}", response_model=UploadSessionStatus)
def get_resumable_upload_session(
    upload_session_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadSessionStatus:
    _require_upload_session_access(upload_session_id, current_user)
    return _upload_session_status(upload_session_id)


@router.put("/upload-sessions/{upload_session_id}/parts/{part_number}", response_model=UploadSessionStatus)
def put_resumable_upload_part(
    upload_session_id: UUID,
    part_number: int,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadSessionStatus:
    _require_upload_session_access(upload_session_id, current_user)
    save_upload_part(upload_session_id, part_number, file)
    return _upload_session_status(upload_session_id)


@router.post(
    "/upload-sessions/{upload_session_id}/complete",
    response_model=ProcessingJobStatus,
    status_code=202,
)
def complete_resumable_upload_session(
    upload_session_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessingJobStatus:
    _require_upload_session_access(upload_session_id, current_user)
    session, path = assemble_upload_session(upload_session_id)
    job = create_processing_job(
        path=path,
        file_name=session.file_name,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        uploaded_by_user_id=current_user.app_user_id,
        visibility=session.visibility,
        allowed_role_names=session.allowed_role_names,
        force_ocr=session.force_ocr,
    )
    enqueue_processing_job(job.job_id)
    return job.to_status()


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentDetail:
    persisted = get_persisted_document(document_id, current_user)
    if persisted is not None:
        return persisted

    document = document_store.get_document(document_id)
    if document is None or not _is_document_summary_authorized(document, current_user):
        raise HTTPException(status_code=404, detail="Document not found")
    authorized_chunks = [
        chunk
        for chunk in document.chunks
        if is_chunk_authorized(
            chunk,
            str(current_user.tenant_id),
            current_user.roles,
            current_user.keycloak_subject,
        )
    ]
    return DocumentDetail(**document.model_dump(exclude={"chunks"}), chunks=authorized_chunks)


@router.get("/{document_id}/chunks", response_model=DocumentChunksResponse)
def get_document_chunks(
    document_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentChunksResponse:
    all_chunks = document_store.get_chunks(document_id)
    authorized_chunks = [
        chunk
        for chunk in all_chunks
        if is_chunk_authorized(
            chunk,
            str(current_user.tenant_id),
            current_user.roles,
            current_user.keycloak_subject,
        )
    ]
    # Don't distinguish "doesn't exist" from "not authorized" -- both 404, so
    # callers can't probe for the existence of documents in other tenants.
    if all_chunks and not authorized_chunks:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentChunksResponse(document_id=document_id, chunks=authorized_chunks)


def _save_upload(file: UploadFile) -> tuple[Path, str]:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    _validate_upload_extension(safe_name)
    target = upload_dir / f"{uuid4()}-{safe_name}"
    bytes_written = 0
    with target.open("wb") as output:
        while chunk := file.file.read(UPLOAD_COPY_CHUNK_SIZE):
            bytes_written += len(chunk)
            if bytes_written > settings.max_upload_bytes:
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Uploaded file exceeds the {settings.max_upload_bytes} byte limit"
                    ),
                )
            output.write(chunk)
    return target, safe_name


def _validate_upload_extension(file_name: str) -> None:
    suffix = Path(file_name).suffix.lower()
    allowed = {
        extension.strip().lower()
        for extension in get_settings().allowed_upload_extensions.split(",")
        if extension.strip()
    }
    if suffix not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix or 'none'}'. Allowed extensions: {allowed_list}",
        )


def _resolve_ingest_path(raw_path: str) -> Path:
    normalized = raw_path.strip()
    if normalized.startswith("file://"):
        parsed = urlparse(normalized)
        normalized = unquote(parsed.path)

    host_prefix = get_settings().host_mount_source_prefix.strip()
    if host_prefix:
        host_prefix = host_prefix.rstrip("/") + "/"
        if normalized.startswith(host_prefix):
            return Path("/host-downloads") / normalized.removeprefix(host_prefix)

    return Path(normalized)


def _is_document_summary_authorized(
    document: DocumentSummary,
    current_user: AuthenticatedUser,
) -> bool:
    if document.tenant_id != current_user.tenant_id:
        return False
    if document.visibility == "tenant":
        return True
    if document.visibility == "private":
        return document.uploaded_by == current_user.keycloak_subject
    return bool(set(document.allowed_role_names).intersection(current_user.roles))
