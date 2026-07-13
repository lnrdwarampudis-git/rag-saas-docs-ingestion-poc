from pathlib import Path
from uuid import UUID
from typing import Any
import hashlib
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.auth.models import AuthenticatedUser
from app.rag.retrieval import is_chunk_authorized
from app.schemas.documents import ChunkDTO, DocumentDetail, DocumentSummary

logger = logging.getLogger(__name__)


def persist_document_ingestion(
    *,
    document_id: UUID,
    tenant_id: UUID,
    path: Path,
    file_name: str,
    mime_type: str | None,
    visibility: str,
    allowed_role_names: list[str],
    force_ocr: bool,
    ocr_used: bool,
    extraction_warnings: list[str],
    extraction_ms: float,
    ocr_ms: float,
    ocr_pages: int,
    chunks: list[ChunkDTO],
    uploaded_by_user_id: UUID | None = None,
) -> None:
    if not get_settings().enable_db_persistence:
        return

    content_hash = _sha256(path)
    byte_size = path.stat().st_size
    source_uri = str(path)
    status = "embedded" if chunks else "failed"
    extraction_metadata = {
        "chunk_count": len(chunks),
        "ocr_used": ocr_used,
        "extraction_warnings": extraction_warnings,
        "extraction_ms": extraction_ms,
        "ocr_ms": ocr_ms,
        "ocr_pages": ocr_pages,
        "source": "upload_or_mounted_path",
    }

    try:
        from app.db import engine

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                      id, tenant_id, source_uri, file_name, mime_type, content_sha256,
                      byte_size, status, visibility, allowed_role_names, ocr_required,
                      extraction_metadata, uploaded_by, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :source_uri, :file_name, :mime_type, :content_sha256,
                      :byte_size, CAST(:status AS document_status), CAST(:visibility AS visibility),
                      CAST(:allowed_role_names AS text[]), :ocr_required,
                      CAST(:extraction_metadata AS jsonb), :uploaded_by, now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      mime_type = EXCLUDED.mime_type,
                      content_sha256 = EXCLUDED.content_sha256,
                      byte_size = EXCLUDED.byte_size,
                      status = EXCLUDED.status,
                      visibility = EXCLUDED.visibility,
                      allowed_role_names = EXCLUDED.allowed_role_names,
                      ocr_required = EXCLUDED.ocr_required,
                      extraction_metadata = EXCLUDED.extraction_metadata,
                      uploaded_by = EXCLUDED.uploaded_by,
                      updated_at = now()
                    """
                ),
                {
                    "id": document_id,
                    "tenant_id": tenant_id,
                    "source_uri": source_uri,
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "content_sha256": content_hash,
                    "byte_size": byte_size,
                    "status": status,
                    "visibility": visibility,
                    "allowed_role_names": allowed_role_names,
                    "ocr_required": force_ocr,
                    "extraction_metadata": _json_string(extraction_metadata),
                    "uploaded_by": uploaded_by_user_id,
                },
            )
            for chunk in chunks:
                connection.execute(
                    text(
                        """
                        INSERT INTO document_chunks (
                          tenant_id, document_id, chunk_index, text, token_count,
                          section_title, visibility, allowed_role_names, ocr_used,
                          source_metadata
                        )
                        VALUES (
                          :tenant_id, :document_id, :chunk_index, :text, :token_count,
                          :section_title, CAST(:visibility AS visibility),
                          CAST(:allowed_role_names AS text[]), :ocr_used,
                          CAST(:source_metadata AS jsonb)
                        )
                        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                          text = EXCLUDED.text,
                          token_count = EXCLUDED.token_count,
                          source_metadata = EXCLUDED.source_metadata
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "document_id": document_id,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "token_count": chunk.token_count,
                        "section_title": chunk.metadata.get("section_title"),
                        "visibility": visibility,
                        "allowed_role_names": allowed_role_names,
                        "ocr_used": bool(chunk.metadata.get("ocr_used", False)),
                        "source_metadata": _json_string(chunk.metadata),
                    },
                )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                      tenant_id, action, resource_type, resource_id, metadata
                    )
                    VALUES (
                      :tenant_id, 'document.ingested', 'document', :resource_id,
                      CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "resource_id": document_id,
                    "metadata": _json_string(
                        {
                            "file_name": file_name,
                            "chunks_created": len(chunks),
                            "ocr_used": ocr_used,
                            "warning_count": len(extraction_warnings),
                            "extraction_ms": extraction_ms,
                            "ocr_ms": ocr_ms,
                            "ocr_pages": ocr_pages,
                        }
                    ),
                },
            )
    except SQLAlchemyError:
        logger.exception("Failed to persist document ingestion for %s", document_id)
        return


def persist_processing_job_created(job: Any) -> None:
    if not get_settings().enable_db_persistence:
        return

    try:
        from app.db import engine

        content_hash = _sha256(job.path)
        byte_size = job.path.stat().st_size
        metadata = {
            "source": "async_upload",
            "force_ocr": job.force_ocr,
            "uploaded_by_subject": job.uploaded_by,
        }
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                      id, tenant_id, source_uri, file_name, mime_type, content_sha256,
                      byte_size, status, visibility, allowed_role_names, ocr_required,
                      extraction_metadata, uploaded_by, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :source_uri, :file_name, NULL, :content_sha256,
                      :byte_size, 'pending', CAST(:visibility AS visibility),
                      CAST(:allowed_role_names AS text[]), :ocr_required,
                      CAST(:extraction_metadata AS jsonb), :uploaded_by, now()
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": job.document_id,
                    "tenant_id": job.tenant_id,
                    "source_uri": str(job.path),
                    "file_name": job.file_name,
                    "content_sha256": content_hash,
                    "byte_size": byte_size,
                    "visibility": job.visibility,
                    "allowed_role_names": job.allowed_role_names,
                    "ocr_required": job.force_ocr,
                    "extraction_metadata": _json_string(metadata),
                    "uploaded_by": job.uploaded_by_user_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO processing_jobs (
                      id, tenant_id, document_id, stage, status, attempts, error_message,
                      started_at, finished_at, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :document_id, CAST(:stage AS processing_stage),
                      :status, :attempts, :error_message, :started_at, :finished_at,
                      COALESCE(:created_at, now())
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      status = EXCLUDED.status,
                      stage = EXCLUDED.stage,
                      attempts = EXCLUDED.attempts,
                      error_message = EXCLUDED.error_message,
                      started_at = EXCLUDED.started_at,
                      finished_at = EXCLUDED.finished_at
                    """
                ),
                _job_params(job),
            )
    except SQLAlchemyError:
        logger.exception("Failed to persist processing job %s", job.job_id)


def persist_processing_job_update(job: Any) -> None:
    if not get_settings().enable_db_persistence:
        return

    try:
        from app.db import engine

        document_status = {
            "queued": "pending",
            "processing": "extracting" if job.stage in {"upload", "extract", "ocr"} else "chunking",
            "completed": "embedded",
            "failed": "failed",
        }.get(job.status, "pending")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE processing_jobs
                    SET status = :status,
                        stage = CAST(:stage AS processing_stage),
                        attempts = :attempts,
                        error_message = :error_message,
                        started_at = :started_at,
                        finished_at = :finished_at
                    WHERE id = :id
                    """
                ),
                _job_params(job),
            )
            connection.execute(
                text(
                    """
                    UPDATE documents
                    SET status = CAST(:status AS document_status),
                        updated_at = now()
                    WHERE id = :document_id
                    """
                ),
                {"document_id": job.document_id, "status": document_status},
            )
    except SQLAlchemyError:
        logger.exception("Failed to update processing job %s", job.job_id)


def get_persisted_processing_job(job_id: UUID):
    if not get_settings().enable_db_persistence:
        return None

    try:
        from app.db import engine
        from app.rag.jobs import ProcessingJob

        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                      j.id AS job_id,
                      j.tenant_id,
                      j.document_id,
                      j.stage::text AS stage,
                      j.status,
                      j.attempts,
                      j.error_message,
                      j.started_at,
                      j.finished_at,
                      j.created_at,
                      d.source_uri,
                      d.file_name,
                      d.visibility::text AS visibility,
                      d.allowed_role_names,
                      d.ocr_required,
                      d.uploaded_by,
                      d.extraction_metadata
                    FROM processing_jobs j
                    JOIN documents d ON d.id = j.document_id
                    WHERE j.id = :job_id
                    """
                ),
                {"job_id": job_id},
            ).mappings().first()
            if row is None:
                return None

            metadata = dict(row["extraction_metadata"] or {})
            return ProcessingJob(
                job_id=row["job_id"],
                document_id=row["document_id"],
                tenant_id=row["tenant_id"],
                path=Path(row["source_uri"]),
                file_name=row["file_name"],
                visibility=row["visibility"],
                allowed_role_names=list(row["allowed_role_names"] or []),
                force_ocr=bool(row["ocr_required"]),
                uploaded_by=metadata.get("uploaded_by_subject") or "",
                uploaded_by_user_id=row["uploaded_by"],
                status=row["status"],
                stage=row["stage"],
                attempts=row["attempts"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
    except SQLAlchemyError:
        logger.exception("Failed to load processing job %s", job_id)
        return None


def load_persisted_chunks() -> list[ChunkDTO]:
    if not get_settings().enable_db_persistence:
        return []

    try:
        from app.db import engine

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                      c.chunk_index,
                      c.text,
                      c.token_count,
                      c.source_metadata,
                      c.tenant_id,
                      c.document_id,
                      c.visibility::text AS visibility,
                      c.allowed_role_names,
                      c.ocr_used,
                      d.file_name,
                      d.mime_type
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.status = 'embedded'
                    ORDER BY c.created_at DESC
                    """
                )
            )
            chunks: list[ChunkDTO] = []
            for row in rows.mappings():
                metadata = dict(row["source_metadata"] or {})
                metadata.update(
                    {
                        "tenant_id": str(row["tenant_id"]),
                        "document_id": str(row["document_id"]),
                        "file_name": row["file_name"],
                        "visibility": row["visibility"],
                        "allowed_role_names": list(row["allowed_role_names"] or []),
                        "ocr_used": row["ocr_used"],
                        "mime_type": row["mime_type"],
                    }
                )
                chunks.append(
                    ChunkDTO(
                        chunk_index=row["chunk_index"],
                        text=row["text"],
                        token_count=row["token_count"],
                        metadata=metadata,
                    )
                )
            return chunks
    except SQLAlchemyError:
        logger.exception("Failed to load persisted document chunks")
        return []


def list_persisted_documents(current_user: AuthenticatedUser) -> list[DocumentSummary]:
    if not get_settings().enable_db_persistence:
        return []

    try:
        from app.db import engine

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                      d.id,
                      d.tenant_id,
                      d.file_name,
                      d.status::text AS status,
                      d.visibility::text AS visibility,
                      d.allowed_role_names,
                      d.byte_size,
                      d.mime_type,
                      d.uploaded_by,
                      d.created_at,
                      d.updated_at,
                      d.extraction_metadata,
                      count(c.id) AS chunk_count,
                      bool_or(c.ocr_used) AS ocr_used,
                      max(c.source_metadata ->> 'uploaded_by') AS uploaded_by_subject,
                      max(a.action) AS latest_audit_action
                    FROM documents d
                    LEFT JOIN document_chunks c ON c.document_id = d.id
                    LEFT JOIN audit_logs a ON a.resource_id = d.id
                    WHERE d.tenant_id = :tenant_id
                    GROUP BY d.id
                    ORDER BY d.created_at DESC
                    LIMIT 200
                    """
                ),
                {"tenant_id": current_user.tenant_id},
            )
            documents: list[DocumentSummary] = []
            for row in rows.mappings():
                summary = _summary_from_row(row)
                if _is_document_summary_authorized(summary, row["uploaded_by"], current_user):
                    documents.append(summary)
            return documents
    except SQLAlchemyError:
        logger.exception("Failed to list persisted documents")
        return []


def get_persisted_document(
    document_id: UUID,
    current_user: AuthenticatedUser,
) -> DocumentDetail | None:
    if not get_settings().enable_db_persistence:
        return None

    try:
        from app.db import engine

        with engine.begin() as connection:
            document_row = connection.execute(
                text(
                    """
                    SELECT
                      d.id,
                      d.tenant_id,
                      d.file_name,
                      d.status::text AS status,
                      d.visibility::text AS visibility,
                      d.allowed_role_names,
                      d.byte_size,
                      d.mime_type,
                      d.uploaded_by,
                      d.created_at,
                      d.updated_at,
                      d.extraction_metadata,
                      count(c.id) AS chunk_count,
                      bool_or(c.ocr_used) AS ocr_used,
                      max(c.source_metadata ->> 'uploaded_by') AS uploaded_by_subject,
                      max(a.action) AS latest_audit_action
                    FROM documents d
                    LEFT JOIN document_chunks c ON c.document_id = d.id
                    LEFT JOIN audit_logs a ON a.resource_id = d.id
                    WHERE d.id = :document_id AND d.tenant_id = :tenant_id
                    GROUP BY d.id
                    """
                ),
                {"document_id": document_id, "tenant_id": current_user.tenant_id},
            ).mappings().first()
            if document_row is None:
                return None

            summary = _summary_from_row(document_row)
            if not _is_document_summary_authorized(summary, document_row["uploaded_by"], current_user):
                return None

            chunk_rows = connection.execute(
                text(
                    """
                    SELECT
                      c.chunk_index,
                      c.text,
                      c.token_count,
                      c.source_metadata,
                      c.tenant_id,
                      c.document_id,
                      c.visibility::text AS visibility,
                      c.allowed_role_names,
                      c.ocr_used,
                      d.file_name,
                      d.mime_type
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.document_id = :document_id AND c.tenant_id = :tenant_id
                    ORDER BY c.chunk_index ASC
                    """
                ),
                {"document_id": document_id, "tenant_id": current_user.tenant_id},
            )
            chunks = [_chunk_from_row(row) for row in chunk_rows.mappings()]
            authorized_chunks = [
                chunk
                for chunk in chunks
                if is_chunk_authorized(
                    chunk,
                    str(current_user.tenant_id),
                    current_user.roles,
                    current_user.keycloak_subject,
                )
            ]
            return DocumentDetail(**summary.model_dump(), chunks=authorized_chunks)
    except SQLAlchemyError:
        logger.exception("Failed to get persisted document %s", document_id)
        return None


def _summary_from_row(row) -> DocumentSummary:
    metadata = dict(row["extraction_metadata"] or {})
    return DocumentSummary(
        document_id=row["id"],
        tenant_id=row["tenant_id"],
        file_name=row["file_name"],
        status=row["status"],
        visibility=row["visibility"],
        allowed_role_names=list(row["allowed_role_names"] or []),
        chunks_created=int(row["chunk_count"] or metadata.get("chunk_count") or 0),
        ocr_used=bool(row["ocr_used"] or metadata.get("ocr_used", False)),
        byte_size=row["byte_size"],
        mime_type=row["mime_type"],
        uploaded_by=row["uploaded_by_subject"],
        extraction_warnings=_extraction_warnings(metadata),
        extraction_ms=_metadata_float(metadata, "extraction_ms"),
        ocr_ms=_metadata_float(metadata, "ocr_ms"),
        ocr_pages=_metadata_int(metadata, "ocr_pages"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        latest_audit_action=row["latest_audit_action"],
    )


def _extraction_warnings(metadata: dict) -> list[str]:
    raw_warnings = metadata.get("extraction_warnings")
    if not isinstance(raw_warnings, list):
        return []
    return [str(warning) for warning in raw_warnings if str(warning).strip()]


def _metadata_float(metadata: dict, key: str) -> float:
    try:
        return float(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _metadata_int(metadata: dict, key: str) -> int:
    try:
        return int(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _chunk_from_row(row) -> ChunkDTO:
    metadata = dict(row["source_metadata"] or {})
    metadata.update(
        {
            "tenant_id": str(row["tenant_id"]),
            "document_id": str(row["document_id"]),
            "file_name": row["file_name"],
            "visibility": row["visibility"],
            "allowed_role_names": list(row["allowed_role_names"] or []),
            "ocr_used": row["ocr_used"],
            "mime_type": row["mime_type"],
        }
    )
    return ChunkDTO(
        chunk_index=row["chunk_index"],
        text=row["text"],
        token_count=row["token_count"],
        metadata=metadata,
    )


def _is_document_summary_authorized(
    document: DocumentSummary,
    uploaded_by_user_id: UUID | None,
    current_user: AuthenticatedUser,
) -> bool:
    if document.visibility == "tenant":
        return True
    if document.visibility == "private":
        return bool(
            (document.uploaded_by and document.uploaded_by == current_user.keycloak_subject)
            or (uploaded_by_user_id and uploaded_by_user_id == current_user.app_user_id)
        )
    return bool(set(document.allowed_role_names).intersection(current_user.roles))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_string(value: dict) -> str:
    import json

    return json.dumps(value)


def _job_params(job: Any) -> dict:
    return {
        "id": job.job_id,
        "tenant_id": job.tenant_id,
        "document_id": job.document_id,
        "stage": job.stage,
        "status": job.status,
        "attempts": job.attempts,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
    }
