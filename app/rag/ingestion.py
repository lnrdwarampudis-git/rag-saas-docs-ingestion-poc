from pathlib import Path
from uuid import UUID, uuid4

from app.config import get_settings
from app.rag.chunking import ChunkingConfig, chunk_text
from app.rag.parsers import extract_document_text
from app.rag.persistence import persist_document_ingestion
from app.rag.store import document_store
from app.schemas.documents import ChunkDTO, DocumentIngestResult


def process_document_path(
    *,
    path: Path,
    tenant_id: UUID,
    uploaded_by: str,
    uploaded_by_user_id: UUID | None,
    visibility: str,
    allowed_role_names: list[str],
    force_ocr: bool,
    file_name: str | None = None,
    document_id: UUID | None = None,
) -> DocumentIngestResult:
    settings = get_settings()
    extraction = extract_document_text(path, force_ocr=force_ocr)
    resolved_document_id = document_id or uuid4()
    resolved_file_name = file_name or path.name

    chunks = chunk_text(
        extraction.text,
        config=ChunkingConfig(
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
        base_metadata={
            "tenant_id": str(tenant_id),
            "document_id": str(resolved_document_id),
            "file_name": resolved_file_name,
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
    document_store.put_chunks(
        resolved_document_id,
        chunk_dtos,
        tenant_id=tenant_id,
        file_name=resolved_file_name,
        status="embedded" if chunk_dtos else "failed",
        visibility=visibility,
        allowed_role_names=allowed_role_names,
        ocr_used=extraction.ocr_used,
        byte_size=path.stat().st_size,
        mime_type=extraction.mime_type,
        uploaded_by=uploaded_by,
    )
    persist_document_ingestion(
        document_id=resolved_document_id,
        tenant_id=tenant_id,
        path=path,
        file_name=resolved_file_name,
        mime_type=extraction.mime_type,
        visibility=visibility,
        allowed_role_names=allowed_role_names,
        force_ocr=force_ocr,
        ocr_used=extraction.ocr_used,
        chunks=chunk_dtos,
        uploaded_by_user_id=uploaded_by_user_id,
    )

    return DocumentIngestResult(
        document_id=resolved_document_id,
        file_name=resolved_file_name,
        chunks_created=len(chunk_dtos),
        ocr_used=extraction.ocr_used,
        extraction_warnings=extraction.warnings,
    )
