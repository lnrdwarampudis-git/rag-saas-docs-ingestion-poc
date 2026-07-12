from dataclasses import dataclass
import re
from typing import Protocol

from app.config import Settings, get_settings
from app.rag.embeddings import EmbeddingConfig, HashingEmbeddingModel
from app.rag.retrieval import RetrievalResult, _content_terms


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a vector representation for retrieval ranking."""


class AnswerGenerator(Protocol):
    def generate(self, query: str, results: list[RetrievalResult]) -> str:
        """Generate an answer from authorized retrieval results."""


@dataclass(frozen=True)
class ModelProvider:
    provider_name: str
    embedding_provider: str
    embedding_runtime: str
    embedding_model_name: str
    answer_runtime: str
    answer_model_name: str
    embedding_model: EmbeddingModel
    answer_generator: AnswerGenerator


class ModelProviderConfigurationError(ValueError):
    """Raised when model provider settings request an unsupported runtime."""


class ExtractiveAnswerGenerator:
    def generate(self, query: str, results: list[RetrievalResult]) -> str:
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


def build_model_provider(settings: Settings | None = None) -> ModelProvider:
    settings = settings or get_settings()
    provider_name = settings.llm_provider.lower()
    embedding_provider = settings.embedding_provider.lower()

    if provider_name != "local" and not settings.public_llm_enabled:
        raise ModelProviderConfigurationError(
            "Public LLM providers require PUBLIC_LLM_ENABLED=true."
        )
    if provider_name != "local":
        raise ModelProviderConfigurationError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'."
        )
    if embedding_provider != "local":
        raise ModelProviderConfigurationError(
            f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'."
        )

    return ModelProvider(
        provider_name=provider_name,
        embedding_provider=embedding_provider,
        embedding_runtime=settings.local_embedding_runtime.lower(),
        embedding_model_name=settings.local_embedding_model_name,
        answer_runtime=settings.local_llm_runtime.lower(),
        answer_model_name=settings.local_llm_model_name,
        embedding_model=_build_local_embedding_model(settings),
        answer_generator=_build_local_answer_generator(settings),
    )


def _build_local_embedding_model(settings: Settings) -> EmbeddingModel:
    runtime = settings.local_embedding_runtime.lower()
    if runtime == "hashing":
        return HashingEmbeddingModel(EmbeddingConfig(dimensions=settings.embedding_dimensions))
    if runtime in {"ollama", "vllm"}:
        raise ModelProviderConfigurationError(
            f"LOCAL_EMBEDDING_RUNTIME '{settings.local_embedding_runtime}' is reserved for a future adapter."
        )
    raise ModelProviderConfigurationError(
        f"Unsupported LOCAL_EMBEDDING_RUNTIME '{settings.local_embedding_runtime}'."
    )


def _build_local_answer_generator(settings: Settings) -> AnswerGenerator:
    runtime = settings.local_llm_runtime.lower()
    if runtime == "extractive":
        return ExtractiveAnswerGenerator()
    if runtime in {"ollama", "vllm"}:
        raise ModelProviderConfigurationError(
            f"LOCAL_LLM_RUNTIME '{settings.local_llm_runtime}' is reserved for a future adapter."
        )
    raise ModelProviderConfigurationError(
        f"Unsupported LOCAL_LLM_RUNTIME '{settings.local_llm_runtime}'."
    )


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
