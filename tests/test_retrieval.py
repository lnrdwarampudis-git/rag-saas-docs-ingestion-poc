from app.rag.embeddings import HashingEmbeddingModel
from app.rag.retrieval import HybridRetriever, RetrievalRequest
from app.rag.vector_index import InMemoryVectorIndex, QdrantVectorIndex
from app.schemas.documents import ChunkDTO
from app.config import Settings
import httpx


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


def test_memory_vector_index_filters_candidates_by_tenant_and_role() -> None:
    index = InMemoryVectorIndex()
    embedding_model = HashingEmbeddingModel()
    chunks = [
        ChunkDTO(
            chunk_index=0,
            text="Finance revenue forecast uses vector search.",
            token_count=6,
            metadata={
                "tenant_id": "tenant-1",
                "document_id": "doc-1",
                "visibility": "role",
                "allowed_role_names": ["finance"],
            },
        ),
        ChunkDTO(
            chunk_index=0,
            text="Other tenant revenue forecast should never leak.",
            token_count=7,
            metadata={
                "tenant_id": "tenant-2",
                "document_id": "doc-2",
                "visibility": "tenant",
                "allowed_role_names": [],
            },
        ),
    ]
    index.upsert_chunks(chunks, embedding_model)

    results = index.search(
        RetrievalRequest(
            query="revenue forecast",
            tenant_id="tenant-1",
            role_names=["finance"],
        ),
        embedding_model,
        candidate_limit=10,
    )

    assert [result.metadata["document_id"] for result in results] == ["doc-1"]


def test_qdrant_vector_index_upserts_and_searches_with_tenant_filter() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        if request.url.path.endswith("/points/search"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "payload": {
                                "chunk_index": 0,
                                "text": "Redis cache improves retrieval latency.",
                                "token_count": 5,
                                "tenant_id": "tenant-1",
                                "document_id": "doc-1",
                                "visibility": "tenant",
                                "allowed_role_names": [],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"result": {"status": "ok"}})

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))
    index = QdrantVectorIndex(
        Settings(_env_file=None, qdrant_url="http://qdrant.test", pgvector_dimensions=8),
        client=client,
    )
    embedding_model = HashingEmbeddingModel()
    chunk = ChunkDTO(
        chunk_index=0,
        text="Redis cache improves retrieval latency.",
        token_count=5,
        metadata={
            "tenant_id": "tenant-1",
            "document_id": "doc-1",
            "visibility": "tenant",
            "allowed_role_names": [],
        },
    )

    index.upsert_chunks([chunk], embedding_model)
    results = index.search(
        RetrievalRequest(query="Redis retrieval", tenant_id="tenant-1", role_names=[]),
        embedding_model,
        candidate_limit=3,
    )

    assert results[0].metadata["document_id"] == "doc-1"
    search_payload = requests[-1].read()
    assert b'"tenant_id"' in search_payload
    assert b'"tenant-1"' in search_payload
