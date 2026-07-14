from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
import hashlib
import logging

import httpx
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


class QdrantVectorIndex:
    backend_name = "qdrant"
    payload_indexes = {
        "tenant_id": "keyword",
        "document_id": "keyword",
        "visibility": "keyword",
        "uploaded_by": "keyword",
        "allowed_role_names": "keyword",
    }

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client or httpx.Client(
            base_url=self.settings.qdrant_url.rstrip("/"),
            timeout=self.settings.qdrant_request_timeout_seconds,
        )

    def upsert_chunks(self, chunks: list[ChunkDTO], embedding_model: EmbeddingModel) -> None:
        if not chunks:
            return
        self._ensure_collection()
        points = []
        for chunk in chunks:
            vector = _fixed_dimensions(
                embedding_model.embed(chunk.text),
                self.settings.pgvector_dimensions,
            )
            payload = {
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "token_count": chunk.token_count,
                **chunk.metadata,
            }
            points.append(
                {
                    "id": _qdrant_point_id(chunk),
                    "vector": vector,
                    "payload": payload,
                }
            )
        response = self._client.put(
            f"/collections/{self.settings.qdrant_collection_name}/points",
            json={"points": points},
        )
        response.raise_for_status()

    def search(
        self,
        request: RetrievalRequest,
        embedding_model: EmbeddingModel,
        *,
        candidate_limit: int,
    ) -> list[ChunkDTO]:
        self._ensure_collection()
        response = self._client.post(
            f"/collections/{self.settings.qdrant_collection_name}/points/search",
            json={
                "vector": _fixed_dimensions(
                    embedding_model.embed(request.query),
                    self.settings.pgvector_dimensions,
                ),
                "limit": candidate_limit,
                "with_payload": True,
                "filter": _qdrant_filter(request),
            },
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        chunks = [_chunk_from_qdrant_payload(item.get("payload", {})) for item in results]
        return [
            chunk
            for chunk in chunks
            if is_chunk_authorized(
                chunk,
                request.tenant_id,
                request.role_names,
                request.requester_subject,
            )
        ]

    def _ensure_collection(self) -> None:
        response = self._client.get(f"/collections/{self.settings.qdrant_collection_name}")
        if response.status_code == 200:
            self.ensure_payload_indexes()
            return
        if response.status_code != 404:
            response.raise_for_status()
        create_response = self._client.put(
            f"/collections/{self.settings.qdrant_collection_name}",
            json={
                "vectors": {
                    "size": self.settings.pgvector_dimensions,
                    "distance": "Cosine",
                }
            },
        )
        create_response.raise_for_status()
        self.ensure_payload_indexes()

    def ensure_payload_indexes(self) -> int:
        ensured = 0
        for field_name, field_schema in self.payload_indexes.items():
            response = self._client.put(
                f"/collections/{self.settings.qdrant_collection_name}/index",
                json={"field_name": field_name, "field_schema": field_schema},
            )
            if response.status_code in {200, 201, 202, 409}:
                ensured += 1
                continue
            response.raise_for_status()
            ensured += 1
        return ensured


memory_vector_index = InMemoryVectorIndex()


def configured_vector_index(settings: Settings | None = None):
    settings = settings or get_settings()
    backend = settings.vector_index_backend.lower()
    if backend == "pgvector":
        return PgVectorIndex(settings)
    if backend == "qdrant":
        return QdrantVectorIndex(settings)
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
    vector = _fixed_dimensions(vector, dimensions)
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _fixed_dimensions(vector: list[float], dimensions: int) -> list[float]:
    if len(vector) < dimensions:
        return [*vector, *([0.0] * (dimensions - len(vector)))]
    if len(vector) > dimensions:
        return vector[:dimensions]
    return vector


def _qdrant_point_id(chunk: ChunkDTO) -> str:
    raw = f"{chunk.metadata.get('tenant_id')}:{chunk.metadata.get('document_id')}:{chunk.chunk_index}"
    digest = hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def _qdrant_filter(request: RetrievalRequest) -> dict:
    should = [{"key": "visibility", "match": {"value": "tenant"}}]
    if request.requester_subject:
        should.append(
            {
                "must": [
                    {"key": "visibility", "match": {"value": "private"}},
                    {"key": "uploaded_by", "match": {"value": request.requester_subject}},
                ]
            }
        )
    if request.role_names:
        should.append(
            {
                "must": [
                    {"key": "visibility", "match": {"value": "role"}},
                    {"key": "allowed_role_names", "match": {"any": request.role_names}},
                ]
            }
        )
    return {
        "must": [{"key": "tenant_id", "match": {"value": request.tenant_id}}],
        "should": should,
    }


def _chunk_from_qdrant_payload(payload: dict) -> ChunkDTO:
    metadata = dict(payload)
    chunk_index = int(metadata.pop("chunk_index", 0))
    text = str(metadata.pop("text", ""))
    token_count = int(metadata.pop("token_count", len(text.split())))
    return ChunkDTO(chunk_index=chunk_index, text=text, token_count=token_count, metadata=metadata)
