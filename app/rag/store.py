from uuid import UUID
from datetime import datetime, timezone

from app.schemas.documents import ChunkDTO, DocumentDetail, DocumentSummary


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._chunks_by_document: dict[UUID, list[ChunkDTO]] = {}
        self._documents: dict[UUID, DocumentSummary] = {}

    def put_chunks(
        self,
        document_id: UUID,
        chunks: list[ChunkDTO],
        *,
        tenant_id: UUID | None = None,
        file_name: str | None = None,
        status: str = "embedded",
        visibility: str = "tenant",
        allowed_role_names: list[str] | None = None,
        ocr_used: bool = False,
        byte_size: int | None = None,
        mime_type: str | None = None,
        uploaded_by: str | None = None,
    ) -> None:
        self._chunks_by_document[document_id] = chunks
        now = datetime.now(timezone.utc)
        existing = self._documents.get(document_id)
        resolved_file_name = file_name or (existing.file_name if existing else str(document_id))
        resolved_tenant_id = tenant_id or _tenant_id_from_chunks(chunks)
        self._documents[document_id] = DocumentSummary(
            document_id=document_id,
            tenant_id=resolved_tenant_id,
            file_name=resolved_file_name,
            status=status,
            visibility=visibility,
            allowed_role_names=allowed_role_names or [],
            chunks_created=len(chunks),
            ocr_used=ocr_used,
            byte_size=byte_size,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            latest_audit_action="document.ingested",
        )

    def get_chunks(self, document_id: UUID) -> list[ChunkDTO]:
        return self._chunks_by_document.get(document_id, [])

    def all_chunks(self) -> list[ChunkDTO]:
        chunks: list[ChunkDTO] = []
        for document_chunks in self._chunks_by_document.values():
            chunks.extend(document_chunks)
        return chunks

    def list_documents(self) -> list[DocumentSummary]:
        return sorted(
            self._documents.values(),
            key=lambda document: document.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def get_document(self, document_id: UUID) -> DocumentDetail | None:
        document = self._documents.get(document_id)
        if document is None:
            return None
        return DocumentDetail(**document.model_dump(), chunks=self.get_chunks(document_id))


document_store = InMemoryDocumentStore()


def _tenant_id_from_chunks(chunks: list[ChunkDTO]) -> UUID:
    for chunk in chunks:
        raw_tenant_id = chunk.metadata.get("tenant_id")
        if raw_tenant_id:
            return UUID(str(raw_tenant_id))
    return UUID("00000000-0000-4000-8000-000000000000")
