from pathlib import Path
import shutil
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.config import get_settings
from app.rag.chunking import ChunkingConfig, chunk_text
from app.rag.parsers import extract_document_text
from app.rag.persistence import persist_document_ingestion
from app.rag.retrieval import is_chunk_authorized
from app.rag.store import document_store
from app.schemas.documents import ChunkDTO, DocumentIngestResult, IngestRequest

router = APIRouter(prefix="/documents", tags=["documents"])

class DocumentChunksResponse(BaseModel):
    document_id: UUID
    chunks: list[ChunkDTO] = Field(default_factory=list)


@router.post("/ingest", response_model=DocumentIngestResult)
def ingest_document(
    payload: IngestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentIngestResult:
    path = _resolve_ingest_path(payload.local_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {payload.local_path}")

    return _process_document_path(
        path=path,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
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
    return _process_document_path(
        path=path,
        file_name=original_file_name,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.keycloak_subject,
        visibility=visibility,
        allowed_role_names=allowed_role_names if visibility == "role" else [],
        force_ocr=force_ocr,
    )


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


def _process_document_path(
    path: Path,
    tenant_id: UUID,
    uploaded_by: str,
    visibility: str,
    allowed_role_names: list[str],
    force_ocr: bool,
    file_name: str | None = None,
) -> DocumentIngestResult:
    settings = get_settings()
    extraction = extract_document_text(path, force_ocr=force_ocr)
    document_id = uuid4()

    chunks = chunk_text(
        extraction.text,
        config=ChunkingConfig(
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
        base_metadata={
            "tenant_id": str(tenant_id),
            "document_id": str(document_id),
            "file_name": file_name or path.name,
            "visibility": visibility,
            "allowed_role_names": allowed_role_names,
            "uploaded_by": uploaded_by,
            "ocr_used": extraction.ocr_used,
            "mime_type": extraction.mime_type,
        },
    )

    chunk_dtos = [
        ChunkDTO(
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            metadata=chunk.metadata,
        )
        for chunk in chunks
    ]
    document_store.put_chunks(document_id, chunk_dtos)
    persist_document_ingestion(
        document_id=document_id,
        tenant_id=tenant_id,
        path=path,
        file_name=file_name or path.name,
        mime_type=extraction.mime_type,
        visibility=visibility,
        allowed_role_names=allowed_role_names,
        force_ocr=force_ocr,
        ocr_used=extraction.ocr_used,
        chunks=chunk_dtos,
    )

    return DocumentIngestResult(
        document_id=document_id,
        file_name=file_name or path.name,
        chunks_created=len(chunk_dtos),
        ocr_used=extraction.ocr_used,
        extraction_warnings=extraction.warnings,
    )


def _save_upload(file: UploadFile) -> tuple[Path, str]:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    target = upload_dir / f"{uuid4()}-{safe_name}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return target, safe_name


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
