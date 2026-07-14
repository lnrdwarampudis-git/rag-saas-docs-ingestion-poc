from uuid import uuid4

from app.rag.pipeline import RagPipeline
from app.rag.store import document_store
from app.schemas.documents import ChunkDTO


def test_pipeline_returns_cached_answer_on_repeat_query() -> None:
    tenant_id = str(uuid4())
    document_store.put_chunks(
        uuid4(),
        [
            ChunkDTO(
                chunk_index=0,
                text="Redis cache improves repeated RAG query latency.",
                token_count=7,
                metadata={
                    "tenant_id": tenant_id,
                    "document_id": "doc-1",
                    "file_name": "architecture.md",
                    "visibility": "tenant",
                    "allowed_role_names": [],
                    "ocr_used": False,
                },
            )
        ],
    )
    pipeline = RagPipeline()

    first = pipeline.answer("How does Redis help?", tenant_id, [])
    second = pipeline.answer("How does Redis help?", tenant_id, [])

    assert first.cached is False
    assert second.cached is True
    assert second.citations[0]["file_name"] == "architecture.md"
    assert "keyword_score" in second.citations[0]
    assert second.metrics["llm_provider"] == "local"
    assert second.metrics["local_llm_runtime"] == "extractive"
    assert second.metrics["embedding_provider"] == "local"
    assert second.metrics["local_embedding_runtime"] == "hashing"
    assert second.metrics["vector_index_backend"] == "memory"
    assert second.metrics["reranker_provider"] == "none"


def test_pipeline_extracts_matching_sentence_instead_of_whole_chunk() -> None:
    tenant_id = str(uuid4())
    document_store.put_chunks(
        uuid4(),
        [
            ChunkDTO(
                chunk_index=0,
                text=(
                    "Unrelated setup code prints scaler ranges. "
                    "Knowledge representation is the study of how to encode facts about the world."
                ),
                token_count=18,
                metadata={
                    "tenant_id": tenant_id,
                    "document_id": "doc-2",
                    "file_name": "ai.txt",
                    "visibility": "tenant",
                    "allowed_role_names": [],
                    "ocr_used": False,
                },
            )
        ],
    )
    pipeline = RagPipeline()

    answer = pipeline.answer("What is knowledge representation?", tenant_id, [])

    assert "Knowledge representation is the study" in answer.answer


def test_pipeline_reports_default_reranker_runtime() -> None:
    tenant_id = str(uuid4())
    document_store.put_chunks(
        uuid4(),
        [
            ChunkDTO(
                chunk_index=0,
                text="Vector retrieval candidates can be reranked before answer generation.",
                token_count=9,
                metadata={
                    "tenant_id": tenant_id,
                    "document_id": "doc-3",
                    "file_name": "retrieval.txt",
                    "visibility": "tenant",
                    "allowed_role_names": [],
                    "ocr_used": False,
                },
            )
        ],
    )

    answer = RagPipeline().answer("What can be reranked?", tenant_id, [])

    assert answer.metrics["reranker_provider"] == "none"
    assert answer.metrics["local_reranker_runtime"] == "none"
