from app.rag import backfill_vectors
from app.schemas.documents import ChunkDTO


class RecordingIndex:
    def __init__(self) -> None:
        self.batches: list[list[ChunkDTO]] = []

    def upsert_chunks(self, chunks, embedding_model) -> None:
        self.batches.append(chunks)


def test_vector_backfill_batches_persisted_chunks(monkeypatch) -> None:
    chunks = [
        ChunkDTO(chunk_index=index, text=f"chunk {index}", token_count=2, metadata={})
        for index in range(5)
    ]
    index = RecordingIndex()
    monkeypatch.setattr(backfill_vectors, "load_persisted_chunks", lambda: chunks)
    monkeypatch.setattr(backfill_vectors, "configured_vector_index", lambda settings: index)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "vector_backfill_batch_size", 2)

    assert backfill_vectors.run_backfill() == 5
    assert [len(batch) for batch in index.batches] == [2, 2, 1]
