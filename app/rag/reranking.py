from dataclasses import dataclass
from dataclasses import replace
from typing import Protocol

import httpx

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


class HttpReranker:
    provider_name = "local"

    def __init__(
        self,
        *,
        runtime: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        candidate_multiplier: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.runtime = runtime
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.candidate_multiplier = candidate_multiplier
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout_seconds)

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        if not results:
            return []
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": [result.chunk.text for result in results],
            "top_n": min(top_k, len(results)),
        }
        try:
            response = self._client.post("/rerank", json=payload)
            response.raise_for_status()
            scores = _reranker_scores(response.json(), len(results))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise RerankerConfigurationError(
                f"Local {self.runtime} reranker request failed at {self.base_url}/rerank: "
                f"{exc.__class__.__name__}."
            ) from exc

        reranked = []
        for index, result in enumerate(results):
            score = scores.get(index, result.score)
            reranked.append(replace(result, score=float(score)))
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
        return HttpReranker(
            runtime=runtime,
            model_name=settings.local_reranker_model_name
            if settings.local_reranker_model_name != "none"
            else runtime,
            base_url=settings.local_reranker_base_url,
            timeout_seconds=settings.local_reranker_request_timeout_seconds,
            candidate_multiplier=settings.reranker_candidate_multiplier,
        )
    raise RerankerConfigurationError(
        f"Unsupported LOCAL_RERANKER_RUNTIME '{settings.local_reranker_runtime}'."
    )


def _reranker_scores(payload: dict, result_count: int) -> dict[int, float]:
    raw_results = payload.get("results") or payload.get("data")
    if isinstance(raw_results, list):
        scores = {}
        for position, item in enumerate(raw_results):
            if not isinstance(item, dict):
                continue
            index = item.get("index", position)
            score = item.get("relevance_score", item.get("score"))
            if isinstance(index, int) and 0 <= index < result_count and isinstance(score, (int, float)):
                scores[index] = float(score)
        if scores:
            return scores

    raw_scores = payload.get("scores")
    if isinstance(raw_scores, list):
        return {
            index: float(score)
            for index, score in enumerate(raw_scores[:result_count])
            if isinstance(score, (int, float))
        }
    raise ValueError("reranker response did not include scores")
