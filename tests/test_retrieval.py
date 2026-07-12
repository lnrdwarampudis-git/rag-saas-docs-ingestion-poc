from app.rag.retrieval import HybridRetriever, RetrievalRequest
from app.schemas.documents import ChunkDTO


def test_retrieval_filters_role_restricted_chunks() -> None:
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="Finance policy says revenue forecasts are confidential.",
            token_count=7,
            metadata={
                "tenant_id": "tenant-1",
                "visibility": "role",
                "allowed_role_names": ["finance"],
            },
        ),
        ChunkDTO(
            chunk_index=1,
            text="Engineering deploys services on Fridays.",
            token_count=5,
            metadata={
                "tenant_id": "tenant-1",
                "visibility": "tenant",
                "allowed_role_names": [],
            },
        ),
    ]

    results = HybridRetriever().retrieve(
        chunks,
        RetrievalRequest(query="revenue forecasts", tenant_id="tenant-1", role_names=["engineering"]),
    )

    assert all(result.chunk.chunk_index != 0 for result in results)


def test_retrieval_returns_best_matching_authorized_chunk() -> None:
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="Benefits enrollment and payroll deadlines.",
            token_count=5,
            metadata={"tenant_id": "tenant-1", "visibility": "tenant", "allowed_role_names": []},
        ),
        ChunkDTO(
            chunk_index=1,
            text="The RAG pipeline uses Redis cache and vector retrieval.",
            token_count=9,
            metadata={"tenant_id": "tenant-1", "visibility": "tenant", "allowed_role_names": []},
        ),
    ]

    results = HybridRetriever().retrieve(
        chunks,
        RetrievalRequest(query="Redis vector retrieval", tenant_id="tenant-1", role_names=[]),
    )

    assert results[0].chunk.chunk_index == 1
    assert results[0].keyword_score > 0


def test_retrieval_rejects_unrelated_hash_similarity() -> None:
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="print scaler minimum maximum feature ranges after normalization.",
            token_count=8,
            metadata={"tenant_id": "tenant-1", "visibility": "tenant", "allowed_role_names": []},
        )
    ]

    results = HybridRetriever().retrieve(
        chunks,
        RetrievalRequest(query="What is knowledge representation?", tenant_id="tenant-1", role_names=[]),
    )

    assert results == []


def test_retrieval_respects_minimum_keyword_overlap() -> None:
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="Redis appears once in a broad unrelated operations memo.",
            token_count=9,
            metadata={"tenant_id": "tenant-1", "visibility": "tenant", "allowed_role_names": []},
        )
    ]

    results = HybridRetriever(min_keyword_overlap=0.75).retrieve(
        chunks,
        RetrievalRequest(query="Redis vector retrieval", tenant_id="tenant-1", role_names=[]),
    )

    assert results == []


def test_retrieval_matches_pdf_split_words() -> None:
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="What is a kno wledge represen tation? A representation is a surrogate for reasoning.",
            token_count=13,
            metadata={"tenant_id": "tenant-1", "visibility": "tenant", "allowed_role_names": []},
        )
    ]

    results = HybridRetriever().retrieve(
        chunks,
        RetrievalRequest(query="What is knowledge representation?", tenant_id="tenant-1", role_names=[]),
    )

    assert results[0].chunk.chunk_index == 0
