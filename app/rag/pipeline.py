from dataclasses import dataclass
import hashlib
import re
import time

from app.rag.cache import QueryCache, cache_key
from app.rag.persistence import load_persisted_chunks
from app.rag.retrieval import HybridRetriever, RetrievalRequest, RetrievalResult, _content_terms
from app.rag.store import document_store

SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    cached: bool
    citations: list[dict]
    metrics: dict[str, float | int]


class RagPipeline:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        cache: QueryCache | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.cache = cache or QueryCache()

    def answer(
        self,
        query: str,
        tenant_id: str,
        role_names: list[str],
        top_k: int = 5,
    ) -> RagAnswer:
        started = time.perf_counter()
        key = cache_key(
            {
                "query": query,
                "tenant_id": tenant_id,
                "role_names": sorted(role_names),
                "top_k": top_k,
            }
        )
        cached = self.cache.get(key)
        if cached is not None:
            cached["cached"] = True
            return RagAnswer(**cached)

        retrieval_started = time.perf_counter()
        chunks = _dedupe_chunks([*document_store.all_chunks(), *load_persisted_chunks()])
        results = self.retriever.retrieve(
            chunks,
            RetrievalRequest(query=query, tenant_id=tenant_id, role_names=role_names, top_k=top_k),
        )
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        answer = _compose_precise_answer(query, results)
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
            },
        }
        self.cache.set(key, payload)
        return RagAnswer(**payload)


def _compose_precise_answer(query: str, results: list[RetrievalResult]) -> str:
    if not results:
        return (
            "I could not find enough authorized context to answer this precisely. "
            "Upload relevant documents or check your role access."
        )

    query_terms = _content_terms(query)
    matched_sentences: list[str] = []
    for result in results:
        sentences = SENTENCE_PATTERN.split(result.chunk.text.strip())
        for sentence in sentences:
            sentence_terms = _content_terms(sentence)
            if query_terms.intersection(sentence_terms):
                matched_sentences.append(" ".join(sentence.split()))
            if len(matched_sentences) >= 3:
                break
        if len(matched_sentences) >= 3:
            break

    if not matched_sentences:
        return (
            "I found authorized context, but not enough matching evidence to answer precisely. "
            "Try a more specific question or upload a more relevant document."
        )

    answer = _clean_answer_text(" ".join(matched_sentences))
    trimmed = " ".join(answer.split()[:160])
    return f"Based on matching authorized context for '{query}': {trimmed}"


def _dedupe_chunks(chunks: list) -> list:
    deduped = {}
    for chunk in chunks:
        metadata = chunk.metadata
        text_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        key = (metadata.get("file_name"), chunk.chunk_index, text_hash)
        deduped[key] = chunk
    return list(deduped.values())


def _clean_answer_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)
    replacements = {
        r"\bkno\s+wledge\b": "knowledge",
        r"\brepresen\s+tation\b": "representation",
        r"\brepresen\s+tation's\b": "representation's",
        r"\bIn\s+tro\s+duction\b": "Introduction",
        r"\bW\s+e\b": "We",
        r"\bb\s+est\b": "best",
        r"\bb\s+e\b": "be",
        r"\bundersto\s+o\s+d\b": "understood",
        r"\bfundamen\s+tally\b": "fundamentally",
        r"\bsubsti-\s*tute\b": "substitute",
        r"\ben\s+tit\s+y\b": "entity",
        r"\bb\s+y\b": "by",
        r"\bab\s+out\b": "about",
        r"\bw\s+orld\b": "world",
        r"\bfragmenta\s+ry\b": "fragmentary",
        r"\btheo\s+ry\b": "theory",
        r"\bin\s+telligen\s+t\b": "intelligent",
        r"\bcomp\s+onen\s+ts\b": "components",
        r"\bpla\s+ys\b": "plays",
        r"\bv\s+e\b": "five",
    }
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _citation(result: RetrievalResult) -> dict:
    metadata = result.chunk.metadata
    return {
        "document_id": metadata.get("document_id"),
        "file_name": metadata.get("file_name"),
        "section_title": metadata.get("section_title"),
        "chunk_index": result.chunk.chunk_index,
        "score": round(result.score, 4),
        "ocr_used": metadata.get("ocr_used", False),
    }
