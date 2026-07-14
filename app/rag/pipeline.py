from dataclasses import dataclass
from dataclasses import replace
import hashlib
import time

from app.rag.analytics import record_query_event
from app.rag.cache import QueryCache, cache_key
from app.rag.model_providers import ModelProvider, build_model_provider
from app.rag.persistence import load_persisted_chunks
from app.rag.reranking import Reranker, build_reranker
from app.rag.retrieval import HybridRetriever, RetrievalRequest, RetrievalResult
from app.rag.store import document_store
from app.rag.vector_index import configured_vector_index


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    cached: bool
    citations: list[dict]
    metrics: dict[str, float | int | str]


class RagPipeline:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        cache: QueryCache | None = None,
        model_provider: ModelProvider | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.model_provider = model_provider or build_model_provider()
        self.retriever = retriever or HybridRetriever(
            embedding_model=self.model_provider.embedding_model
        )
        self.cache = cache or QueryCache()
        self.reranker = reranker or build_reranker()

    def answer(
        self,
        query: str,
        tenant_id: str,
        role_names: list[str],
        top_k: int = 5,
        requester_subject: str | None = None,
    ) -> RagAnswer:
        started = time.perf_counter()
        key = cache_key(
            {
                "query": query,
                "tenant_id": tenant_id,
                "role_names": sorted(role_names),
                "requester_subject": requester_subject,
                "top_k": top_k,
                "llm_provider": self.model_provider.provider_name,
                "local_llm_runtime": self.model_provider.answer_runtime,
                "answer_model": self.model_provider.answer_model_name,
                "embedding_provider": self.model_provider.embedding_provider,
                "local_embedding_runtime": self.model_provider.embedding_runtime,
                "embedding_model": self.model_provider.embedding_model_name,
                "reranker_provider": self.reranker.provider_name,
                "local_reranker_runtime": self.reranker.runtime,
                "reranker_model": self.reranker.model_name,
            }
        )
        cached = self.cache.get(key)
        if cached is not None:
            cached["cached"] = True
            record_query_event(
                tenant_id=tenant_id,
                cached=True,
                retrieval_ms=cached.get("metrics", {}).get("retrieval_ms"),
                total_ms=cached.get("metrics", {}).get("total_ms"),
            )
            return RagAnswer(**cached)

        retrieval_started = time.perf_counter()
        request = RetrievalRequest(
            query=query,
            tenant_id=tenant_id,
            role_names=role_names,
            requester_subject=requester_subject,
            top_k=top_k,
        )
        candidate_limit = max(top_k, top_k * max(1, self.reranker.candidate_multiplier))
        vector_index = configured_vector_index()
        indexed_chunks = vector_index.search(
            request,
            self.model_provider.embedding_model,
            candidate_limit=candidate_limit,
        )
        chunks = indexed_chunks or _dedupe_chunks([*document_store.all_chunks(), *load_persisted_chunks()])
        results = self.retriever.retrieve(
            chunks,
            replace(request, top_k=candidate_limit),
        )
        results = self.reranker.rerank(query, results, top_k)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        answer = self.model_provider.answer_generator.generate(query, results)
        citations = [_citation(result) for result in results]
        total_ms = (time.perf_counter() - started) * 1000

        payload = {
            "answer": answer,
            "cached": False,
            "citations": citations,
            "metrics": {
                "retrieval_ms": round(retrieval_ms, 3),
                "total_ms": round(total_ms, 3),
                "contexts_used": len(results),
                "top_score": round(results[0].score, 4) if results else 0,
                "retrieval_min_score": self.retriever.min_score,
                "retrieval_min_keyword_overlap": self.retriever.min_keyword_overlap,
                "vector_index_backend": vector_index.backend_name,
                "reranker_provider": self.reranker.provider_name,
                "local_reranker_runtime": self.reranker.runtime,
                "reranker_model": self.reranker.model_name,
                "llm_provider": self.model_provider.provider_name,
                "local_llm_runtime": self.model_provider.answer_runtime,
                "embedding_provider": self.model_provider.embedding_provider,
                "local_embedding_runtime": self.model_provider.embedding_runtime,
                "embedding_model": self.model_provider.embedding_model_name,
                "answer_model": self.model_provider.answer_model_name,
            },
        }
        self.cache.set(key, payload)
        record_query_event(
            tenant_id=tenant_id,
            cached=False,
            retrieval_ms=payload["metrics"]["retrieval_ms"],
            total_ms=payload["metrics"]["total_ms"],
        )
        return RagAnswer(**payload)


def _dedupe_chunks(chunks: list) -> list:
    deduped = {}
    for chunk in chunks:
        metadata = chunk.metadata
        text_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        key = (metadata.get("file_name"), chunk.chunk_index, text_hash)
        deduped[key] = chunk
    return list(deduped.values())


def _citation(result: RetrievalResult) -> dict:
    metadata = result.chunk.metadata
    return {
        "document_id": metadata.get("document_id"),
        "file_name": metadata.get("file_name"),
        "section_title": metadata.get("section_title"),
        "chunk_index": result.chunk.chunk_index,
        "score": round(result.score, 4),
        "keyword_score": round(result.keyword_score, 4),
        "vector_score": round(result.vector_score, 4),
        "early_score": round(result.early_score, 4),
        "ocr_used": metadata.get("ocr_used", False),
    }
