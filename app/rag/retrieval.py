from dataclasses import dataclass
import re
from typing import Iterable, Protocol

from app.config import get_settings
from app.rag.embeddings import HashingEmbeddingModel, cosine_similarity
from app.schemas.documents import ChunkDTO

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a vector representation for retrieval ranking."""


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    tenant_id: str
    role_names: list[str]
    requester_subject: str | None = None
    top_k: int = 5


@dataclass(frozen=True)
class RetrievalResult:
    chunk: ChunkDTO
    score: float
    keyword_score: float
    vector_score: float
    early_score: float


class HybridRetriever:
    def __init__(
        self,
        embedding_model: EmbeddingModel | None = None,
        min_score: float | None = None,
        min_keyword_overlap: float | None = None,
    ) -> None:
        self.embedding_model = embedding_model or HashingEmbeddingModel()
        settings = get_settings()
        self.min_score = settings.retrieval_min_score if min_score is None else min_score
        self.min_keyword_overlap = (
            settings.retrieval_min_keyword_overlap
            if min_keyword_overlap is None
            else min_keyword_overlap
        )

    def retrieve(self, chunks: Iterable[ChunkDTO], request: RetrievalRequest) -> list[RetrievalResult]:
        query_embedding = self.embedding_model.embed(request.query)
        results: list[RetrievalResult] = []
        for chunk in chunks:
            if not is_chunk_authorized(
                chunk, request.tenant_id, request.role_names, request.requester_subject
            ):
                continue
            vector_score = cosine_similarity(query_embedding, self.embedding_model.embed(chunk.text))
            keyword_score = _keyword_overlap(request.query, chunk.text)
            if keyword_score < self.min_keyword_overlap:
                continue
            early_score = _early_term_overlap(request.query, chunk.text)
            score = (0.20 * vector_score) + (0.55 * keyword_score) + (0.25 * early_score)
            if score >= self.min_score:
                results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=score,
                        keyword_score=keyword_score,
                        vector_score=vector_score,
                        early_score=early_score,
                    )
                )

        return sorted(results, key=lambda result: result.score, reverse=True)[: request.top_k]


def is_chunk_authorized(
    chunk: ChunkDTO,
    tenant_id: str,
    role_names: list[str],
    requester_subject: str | None = None,
) -> bool:
    """Single source of truth for chunk-level RBAC: same rule used by retrieval
    ranking and by direct document/chunk lookups, so authorization can't drift
    between the two code paths.
    """
    metadata = chunk.metadata
    if metadata.get("tenant_id") != tenant_id:
        return False
    visibility = metadata.get("visibility", "tenant")
    if visibility == "tenant":
        return True
    if visibility == "private":
        owner = metadata.get("uploaded_by")
        return owner is not None and owner == requester_subject
    allowed_roles = set(metadata.get("allowed_role_names", []))
    return bool(allowed_roles.intersection(role_names))


def _keyword_overlap(query: str, text: str) -> float:
    query_terms = _content_terms(query)
    text_terms = _content_terms(text)
    if not query_terms:
        return 0.0
    return len(query_terms.intersection(text_terms)) / len(query_terms)


def _early_term_overlap(query: str, text: str) -> float:
    query_terms = _content_terms(query)
    early_terms = _content_terms(text[:500])
    if not query_terms:
        return 0.0
    return len(query_terms.intersection(early_terms)) / len(query_terms)


def _content_terms(text: str) -> set[str]:
    raw_terms = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    terms = {token for token in raw_terms if token not in STOPWORDS}
    terms.update(_joined_split_terms(raw_terms))
    return terms


def _joined_split_terms(raw_terms: list[str]) -> set[str]:
    joined_terms: set[str] = set()
    for index, term in enumerate(raw_terms[:-1]):
        next_term = raw_terms[index + 1]
        if term in STOPWORDS or next_term in STOPWORDS:
            continue
        if term.isalpha() and next_term.isalpha() and len(term) >= 2 and len(next_term) >= 2:
            joined_terms.add(term + next_term)
    return joined_terms
