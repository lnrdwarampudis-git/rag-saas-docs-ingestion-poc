from dataclasses import dataclass
from dataclasses import replace
from typing import Protocol

from app.config import Settings, get_settings
from app.rag.retrieval import RetrievalResult, _keyword_overlap


class Reranker(Protocol):
    provider_name: str
    runtime: str
    model_name: str
    candidate_multiplier: int

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        """Return retrieval results ordered by final rank."""


@dataclass(frozen=True)
class NoopReranker:
    provider_name: str = "none"
    runtime: str = "none"
    model_name: str = "none"
    candidate_multiplier: int = 4

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        return results[:top_k]


@dataclass(frozen=True)
class KeywordReranker:
    provider_name: str = "local"
    runtime: str = "keyword"
    model_name: str = "keyword-overlap"
    candidate_multiplier: int = 4

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        reranked = []
        for result in results:
            rerank_score = _keyword_overlap(query, result.chunk.text)
            final_score = (0.70 * result.score) + (0.30 * rerank_score)
            reranked.append(replace(result, score=final_score))
        return sorted(reranked, key=lambda result: result.score, reverse=True)[:top_k]


class RerankerConfigurationError(ValueError):
    """Raised when reranker settings request an unsupported runtime."""


def build_reranker(settings: Settings | None = None) -> Reranker:
    settings = settings or get_settings()
    provider = settings.reranker_provider.lower()
    runtime = settings.local_reranker_runtime.lower()
    if provider == "none":
        return NoopReranker(candidate_multiplier=settings.reranker_candidate_multiplier)
    if provider != "local":
        raise RerankerConfigurationError(
            f"Unsupported RERANKER_PROVIDER '{settings.reranker_provider}'."
        )
    if runtime == "keyword":
        return KeywordReranker(
            model_name=settings.local_reranker_model_name
            if settings.local_reranker_model_name != "none"
            else "keyword-overlap",
            candidate_multiplier=settings.reranker_candidate_multiplier,
        )
    if runtime in {"cross-encoder", "vllm"}:
        raise RerankerConfigurationError(
            f"LOCAL_RERANKER_RUNTIME '{settings.local_reranker_runtime}' is reserved for a future adapter."
        )
    raise RerankerConfigurationError(
        f"Unsupported LOCAL_RERANKER_RUNTIME '{settings.local_reranker_runtime}'."
    )
