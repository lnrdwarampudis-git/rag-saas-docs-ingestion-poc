import pytest

from app.config import Settings
from app.rag.reranking import KeywordReranker, RerankerConfigurationError, build_reranker
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


def test_cross_encoder_reranker_remains_reserved_until_adapter_exists() -> None:
    with pytest.raises(RerankerConfigurationError, match="reserved"):
        build_reranker(
            Settings(
                _env_file=None,
                reranker_provider="local",
                local_reranker_runtime="cross-encoder",
            )
        )
