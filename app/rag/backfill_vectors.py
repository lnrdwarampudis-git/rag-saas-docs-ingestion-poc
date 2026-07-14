from app.config import get_settings
from app.rag.model_providers import build_model_provider
from app.rag.persistence import load_persisted_chunks
from app.rag.vector_index import configured_vector_index
from app.schemas.documents import ChunkDTO


def run_backfill() -> int:
    settings = get_settings()
    chunks = load_persisted_chunks()
    provider = build_model_provider(settings)
    index = configured_vector_index(settings)
    updated = 0
    for batch in _batches(chunks, settings.vector_backfill_batch_size):
        index.upsert_chunks(batch, provider.embedding_model)
        updated += len(batch)
    return updated


def _batches(chunks: list[ChunkDTO], batch_size: int) -> list[list[ChunkDTO]]:
    size = max(1, batch_size)
    return [chunks[index : index + size] for index in range(0, len(chunks), size)]


if __name__ == "__main__":
    count = run_backfill()
    print(f"Backfilled vector index for {count} chunks.")
