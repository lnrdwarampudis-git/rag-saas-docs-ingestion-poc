import httpx

from app.config import Settings
from app.rag.reranking import HttpReranker, KeywordReranker, build_reranker
from app.rag.retrieval import RetrievalResult
from app.schemas.documents import ChunkDTO


def test_keyword_reranker_is_available_for_local_ranking() -> None:
    reranker = build_reranker(
        Settings(
            _env_file=None,
            reranker_provider="local",
            local_reranker_runtime="keyword",
            local_reranker_model_name="keyword-overlap",
        )
    )

    assert isinstance(reranker, KeywordReranker)
    assert reranker.provider_name == "local"
    assert reranker.runtime == "keyword"


def test_keyword_reranker_promotes_stronger_query_overlap() -> None:
    weak = RetrievalResult(
        chunk=ChunkDTO(
            chunk_index=0,
            text="Redis appears in an unrelated platform note.",
            token_count=7,
            metadata={},
        ),
        score=0.50,
        keyword_score=0.2,
        vector_score=0.8,
        early_score=0.2,
    )
    strong = RetrievalResult(
        chunk=ChunkDTO(
            chunk_index=1,
            text="Redis vector retrieval improves repeated query latency.",
            token_count=7,
            metadata={},
        ),
        score=0.45,
        keyword_score=0.8,
        vector_score=0.4,
        early_score=0.8,
    )

    results = KeywordReranker().rerank("Redis vector retrieval", [weak, strong], top_k=2)

    assert results[0].chunk.chunk_index == 1


def test_cross_encoder_reranker_is_available_as_local_http_adapter() -> None:
    reranker = build_reranker(
        Settings(
            _env_file=None,
            reranker_provider="local",
            local_reranker_runtime="cross-encoder",
            local_reranker_model_name="BAAI/bge-reranker-base",
            local_reranker_base_url="http://reranker.test",
        )
    )

    assert isinstance(reranker, HttpReranker)
    assert reranker.runtime == "cross-encoder"


def test_http_reranker_uses_remote_scores() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.9},
                ]
            },
        )

    weak = RetrievalResult(
        chunk=ChunkDTO(chunk_index=0, text="Redis appears once.", token_count=3, metadata={}),
        score=0.8,
        keyword_score=0.2,
        vector_score=0.8,
        early_score=0.2,
    )
    strong = RetrievalResult(
        chunk=ChunkDTO(chunk_index=1, text="Redis vector retrieval latency.", token_count=4, metadata={}),
        score=0.3,
        keyword_score=0.8,
        vector_score=0.3,
        early_score=0.8,
    )
    reranker = HttpReranker(
        runtime="cross-encoder",
        model_name="BAAI/bge-reranker-base",
        base_url="http://reranker.test",
        timeout_seconds=30,
        candidate_multiplier=4,
        client=httpx.Client(base_url="http://reranker.test", transport=httpx.MockTransport(handler)),
    )

    results = reranker.rerank("Redis retrieval", [weak, strong], top_k=2)

    assert requests[0].url.path == "/rerank"
    assert results[0].chunk.chunk_index == 1
