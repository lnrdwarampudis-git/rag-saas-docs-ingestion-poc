from pathlib import Path
from uuid import UUID
import hashlib
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.schemas.documents import ChunkDTO

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
    chunks: list[ChunkDTO],
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
                      extraction_metadata, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :source_uri, :file_name, :mime_type, :content_sha256,
                      :byte_size, CAST(:status AS document_status), CAST(:visibility AS visibility),
                      CAST(:allowed_role_names AS text[]), :ocr_required,
                      CAST(:extraction_metadata AS jsonb), now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      status = EXCLUDED.status,
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
                        }
                    ),
                },
            )
    except SQLAlchemyError:
        logger.exception("Failed to persist document ingestion for %s", document_id)
        return


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_string(value: dict) -> str:
    import json

    return json.dumps(value)
