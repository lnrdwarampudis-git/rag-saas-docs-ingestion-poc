from uuid import UUID

from app.schemas.documents import ChunkDTO


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._chunks_by_document: dict[UUID, list[ChunkDTO]] = {}

    def put_chunks(self, document_id: UUID, chunks: list[ChunkDTO]) -> None:
        self._chunks_by_document[document_id] = chunks

    def get_chunks(self, document_id: UUID) -> list[ChunkDTO]:
        return self._chunks_by_document.get(document_id, [])

    def all_chunks(self) -> list[ChunkDTO]:
        chunks: list[ChunkDTO] = []
        for document_chunks in self._chunks_by_document.values():
            chunks.extend(document_chunks)
        return chunks


document_store = InMemoryDocumentStore()
