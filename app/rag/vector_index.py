from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.rag.embeddings import cosine_similarity
from app.rag.retrieval import EmbeddingModel, RetrievalRequest, is_chunk_authorized
from app.schemas.documents import ChunkDTO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexedChunk:
    chunk: ChunkDTO
    embedding: list[float]


class InMemoryVectorIndex:
    backend_name = "memory"

    def __init__(self) -> None:
        self._chunks: dict[tuple[str, int], IndexedChunk] = {}

    def upsert_chunks(self, chunks: list[ChunkDTO], embedding_model: EmbeddingModel) -> None:
        for chunk in chunks:
            document_id = str(chunk.metadata.get("document_id"))
            self._chunks[(document_id, chunk.chunk_index)] = IndexedChunk(
                chunk=chunk,
                embedding=embedding_model.embed(chunk.text),
            )

    def search(
        self,
        request: RetrievalRequest,
        embedding_model: EmbeddingModel,
        *,
        candidate_limit: int,
    ) -> list[ChunkDTO]:
        query_embedding = embedding_model.embed(request.query)
        scored: list[tuple[float, ChunkDTO]] = []
        for indexed in self._chunks.values():
            if not is_chunk_authorized(
                indexed.chunk,
                request.tenant_id,
                request.role_names,
                request.requester_subject,
            ):
                continue
            scored.append((cosine_similarity(query_embedding, indexed.embedding), indexed.chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:candidate_limit]]


class PgVectorIndex:
    backend_name = "pgvector"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def upsert_chunks(self, chunks: list[ChunkDTO], embedding_model: EmbeddingModel) -> None:
        if not self.settings.enable_db_persistence:
            return
        try:
            from app.db import engine

            with engine.begin() as connection:
                for chunk in chunks:
                    connection.execute(
                        text(
                            """
                            UPDATE document_chunks
                            SET embedding = CAST(:embedding AS vector)
                            WHERE document_id = :document_id AND chunk_index = :chunk_index
                            """
                        ),
                        {
                            "document_id": UUID(str(chunk.metadata["document_id"])),
                            "chunk_index": chunk.chunk_index,
                            "embedding": _pgvector_literal(
                                embedding_model.embed(chunk.text),
                                self.settings.pgvector_dimensions,
                            ),
                        },
                    )
        except (KeyError, SQLAlchemyError, ValueError):
            logger.exception("Failed to update pgvector embeddings")

    def search(
        self,
        request: RetrievalRequest,
        embedding_model: EmbeddingModel,
        *,
        candidate_limit: int,
    ) -> list[ChunkDTO]:
        if not self.settings.enable_db_persistence:
            return []
        try:
            from app.db import engine

            query_embedding = _pgvector_literal(
                embedding_model.embed(request.query),
                self.settings.pgvector_dimensions,
            )
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
                        WHERE
                          d.status = 'embedded'
                          AND c.embedding IS NOT NULL
                          AND c.tenant_id = :tenant_id
                          AND (
                            c.visibility = 'tenant'
                            OR (
                              c.visibility = 'private'
                              AND c.source_metadata ->> 'uploaded_by' = :requester_subject
                            )
                            OR (
                              c.visibility = 'role'
                              AND c.allowed_role_names && CAST(:role_names AS text[])
                            )
                          )
                        ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :candidate_limit
                        """
                    ),
                    {
                        "tenant_id": request.tenant_id,
                        "requester_subject": request.requester_subject,
                        "role_names": request.role_names,
                        "query_embedding": query_embedding,
                        "candidate_limit": candidate_limit,
                    },
                )
                return [_chunk_from_row(row) for row in rows.mappings()]
        except SQLAlchemyError:
            logger.exception("Failed to search pgvector index")
            return []


memory_vector_index = InMemoryVectorIndex()


def configured_vector_index(settings: Settings | None = None):
    settings = settings or get_settings()
    backend = settings.vector_index_backend.lower()
    if backend == "pgvector":
        return PgVectorIndex(settings)
    return memory_vector_index


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


def _pgvector_literal(vector: list[float], dimensions: int) -> str:
    if len(vector) < dimensions:
        vector = [*vector, *([0.0] * (dimensions - len(vector)))]
    elif len(vector) > dimensions:
        vector = vector[:dimensions]
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
