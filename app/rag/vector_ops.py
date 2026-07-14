from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.rag.backfill_vectors import run_backfill
from app.rag.vector_index import QdrantVectorIndex, configured_vector_index


@dataclass(frozen=True)
class VectorOpsResult:
    backend: str
    persistence_ready: bool
    qdrant_payload_indexes: int = 0
    backfilled_chunks: int = 0
    message: str = ""


def run_vector_ops_check(
    *,
    ensure_indexes: bool = True,
    backfill: bool = False,
    settings: Settings | None = None,
) -> VectorOpsResult:
    settings = settings or get_settings()
    backend = settings.vector_index_backend.lower()
    persistence_ready = _persistence_ready(settings)
    qdrant_payload_indexes = 0

    if backend == "qdrant" and ensure_indexes:
        index = configured_vector_index(settings)
        if isinstance(index, QdrantVectorIndex):
            index._ensure_collection()
            qdrant_payload_indexes = index.ensure_payload_indexes()

    backfilled_chunks = run_backfill() if backfill else 0
    return VectorOpsResult(
        backend=backend,
        persistence_ready=persistence_ready,
        qdrant_payload_indexes=qdrant_payload_indexes,
        backfilled_chunks=backfilled_chunks,
        message=_message(backend, persistence_ready, qdrant_payload_indexes, backfilled_chunks),
    )


def _persistence_ready(settings: Settings) -> bool:
    if settings.vector_index_backend.lower() == "memory":
        return True
    if not settings.enable_db_persistence:
        return False
    if settings.vector_index_backend.lower() != "pgvector":
        return True
    try:
        from app.db import engine

        with engine.begin() as connection:
            extension = connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            column = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'document_chunks' AND column_name = 'embedding'
                    """
                )
            ).scalar()
            return bool(extension and column)
    except SQLAlchemyError:
        return False


def _message(
    backend: str,
    persistence_ready: bool,
    qdrant_payload_indexes: int,
    backfilled_chunks: int,
) -> str:
    parts = [f"backend={backend}", f"persistence_ready={persistence_ready}"]
    if qdrant_payload_indexes:
        parts.append(f"qdrant_payload_indexes={qdrant_payload_indexes}")
    if backfilled_chunks:
        parts.append(f"backfilled_chunks={backfilled_chunks}")
    return " ".join(parts)


if __name__ == "__main__":
    result = run_vector_ops_check(backfill=True)
    print(result.message)
