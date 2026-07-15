from dataclasses import dataclass
from json import JSONDecodeError
import math
import re
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.rag.embeddings import EmbeddingConfig, HashingEmbeddingModel
from app.rag.model_profiles import resolve_model_profile
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


class ModelProviderRequestError(RuntimeError):
    """Raised when a configured model provider cannot return a valid response."""


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


class OllamaEmbeddingModel:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def embed(self, text: str) -> list[float]:
        response = _post_ollama_json(
            client=self._client,
            endpoint="/api/embed",
            payload={"model": self.model_name, "input": text},
            model_name=self.model_name,
            base_url=self.base_url,
            operation="embedding",
        )
        embedding = _ollama_embedding_from_response(response.json())
        return _normalize_embedding(embedding)


class OllamaAnswerGenerator:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def generate(self, query: str, results: list[RetrievalResult]) -> str:
        if not results:
            return ExtractiveAnswerGenerator().generate(query, results)

        prompt = _answer_prompt(query, results)
        response = _post_ollama_json(
            client=self._client,
            endpoint="/api/generate",
            payload={"model": self.model_name, "prompt": prompt, "stream": False},
            model_name=self.model_name,
            base_url=self.base_url,
            operation="answer generation",
        )
        answer = response.json().get("response")
        if not isinstance(answer, str) or not answer.strip():
            raise ModelProviderRequestError("Ollama generation response did not include answer text.")
        return answer.strip()


class VllmEmbeddingModel:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def embed(self, text: str) -> list[float]:
        response = _post_json(
            client=self._client,
            endpoint="/v1/embeddings",
            payload={"model": self.model_name, "input": text},
            provider="vLLM",
            model_name=self.model_name,
            base_url=self.base_url,
            operation="embedding",
        )
        embedding = _openai_embedding_from_response(response.json())
        return _normalize_embedding(embedding)


class VllmAnswerGenerator:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def generate(self, query: str, results: list[RetrievalResult]) -> str:
        if not results:
            return ExtractiveAnswerGenerator().generate(query, results)

        response = _post_json(
            client=self._client,
            endpoint="/v1/chat/completions",
            payload={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer using only the authorized context. If there is not enough "
                            "authorized evidence, say so. Keep the answer concise."
                        ),
                    },
                    {"role": "user", "content": _answer_prompt(query, results)},
                ],
                "temperature": 0,
            },
            provider="vLLM",
            model_name=self.model_name,
            base_url=self.base_url,
            operation="answer generation",
        )
        answer = _openai_chat_answer_from_response(response.json())
        if not answer:
            raise ModelProviderRequestError("vLLM generation response did not include answer text.")
        return answer


class OpenAIEmbeddingModel:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers=_authorization_headers(api_key),
        )

    def embed(self, text: str) -> list[float]:
        response = _post_json(
            client=self._client,
            endpoint="/v1/embeddings",
            payload={"model": self.model_name, "input": text},
            provider="OpenAI-compatible",
            model_name=self.model_name,
            base_url=self.base_url,
            operation="embedding",
        )
        embedding = _openai_embedding_from_response(response.json(), provider="OpenAI-compatible")
        return _normalize_embedding(embedding)


class OpenAIAnswerGenerator:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers=_authorization_headers(api_key),
        )

    def generate(self, query: str, results: list[RetrievalResult]) -> str:
        if not results:
            return ExtractiveAnswerGenerator().generate(query, results)

        response = _post_json(
            client=self._client,
            endpoint="/v1/chat/completions",
            payload={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer using only the authorized context. If there is not enough "
                            "authorized evidence, say so. Keep the answer concise."
                        ),
                    },
                    {"role": "user", "content": _answer_prompt(query, results)},
                ],
                "temperature": 0,
            },
            provider="OpenAI-compatible",
            model_name=self.model_name,
            base_url=self.base_url,
            operation="answer generation",
        )
        answer = _openai_chat_answer_from_response(response.json())
        if not answer:
            raise ModelProviderRequestError(
                "OpenAI-compatible generation response did not include answer text."
            )
        return answer


def build_model_provider(settings: Settings | None = None) -> ModelProvider:
    settings = resolve_model_profile(settings or get_settings())
    provider_name = settings.llm_provider.lower()
    embedding_provider = settings.embedding_provider.lower()

    if (provider_name != "local" or embedding_provider != "local") and not settings.public_llm_enabled:
        raise ModelProviderConfigurationError(
            "Public LLM providers require PUBLIC_LLM_ENABLED=true."
        )
    if provider_name not in {"local", "openai"}:
        raise ModelProviderConfigurationError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'."
        )
    if embedding_provider not in {"local", "openai"}:
        raise ModelProviderConfigurationError(
            f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'."
        )

    return ModelProvider(
        provider_name=provider_name,
        embedding_provider=embedding_provider,
        embedding_runtime=(
            settings.local_embedding_runtime.lower()
            if embedding_provider == "local"
            else "openai-compatible"
        ),
        embedding_model_name=(
            settings.local_embedding_model_name
            if embedding_provider == "local"
            else settings.public_embedding_model_name
        ),
        answer_runtime=(
            settings.local_llm_runtime.lower()
            if provider_name == "local"
            else "openai-compatible"
        ),
        answer_model_name=(
            settings.local_llm_model_name
            if provider_name == "local"
            else settings.public_llm_model_name
        ),
        embedding_model=(
            _build_local_embedding_model(settings)
            if embedding_provider == "local"
            else _build_openai_embedding_model(settings)
        ),
        answer_generator=(
            _build_local_answer_generator(settings)
            if provider_name == "local"
            else _build_openai_answer_generator(settings)
        ),
    )


def _build_local_embedding_model(settings: Settings) -> EmbeddingModel:
    runtime = settings.local_embedding_runtime.lower()
    if runtime == "hashing":
        return HashingEmbeddingModel(EmbeddingConfig(dimensions=settings.embedding_dimensions))
    if runtime == "ollama":
        return OllamaEmbeddingModel(
            base_url=settings.local_embedding_base_url,
            model_name=settings.local_embedding_model_name,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    if runtime == "vllm":
        return VllmEmbeddingModel(
            base_url=settings.local_embedding_base_url,
            model_name=settings.local_embedding_model_name,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    raise ModelProviderConfigurationError(
        f"Unsupported LOCAL_EMBEDDING_RUNTIME '{settings.local_embedding_runtime}'."
    )


def _build_local_answer_generator(settings: Settings) -> AnswerGenerator:
    runtime = settings.local_llm_runtime.lower()
    if runtime == "extractive":
        return ExtractiveAnswerGenerator()
    if runtime == "ollama":
        return OllamaAnswerGenerator(
            base_url=settings.local_llm_base_url,
            model_name=settings.local_llm_model_name,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    if runtime == "vllm":
        return VllmAnswerGenerator(
            base_url=settings.local_llm_base_url,
            model_name=settings.local_llm_model_name,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    raise ModelProviderConfigurationError(
        f"Unsupported LOCAL_LLM_RUNTIME '{settings.local_llm_runtime}'."
    )


def _build_openai_embedding_model(settings: Settings) -> EmbeddingModel:
    _require_public_provider_settings(
        settings,
        model_name=settings.public_embedding_model_name,
        model_setting_name="PUBLIC_EMBEDDING_MODEL_NAME",
    )
    return OpenAIEmbeddingModel(
        base_url=settings.public_llm_base_url,
        api_key=settings.public_llm_api_key,
        model_name=settings.public_embedding_model_name,
        timeout_seconds=settings.local_model_request_timeout_seconds,
    )


def _build_openai_answer_generator(settings: Settings) -> AnswerGenerator:
    _require_public_provider_settings(
        settings,
        model_name=settings.public_llm_model_name,
        model_setting_name="PUBLIC_LLM_MODEL_NAME",
    )
    return OpenAIAnswerGenerator(
        base_url=settings.public_llm_base_url,
        api_key=settings.public_llm_api_key,
        model_name=settings.public_llm_model_name,
        timeout_seconds=settings.local_model_request_timeout_seconds,
    )


def _require_public_provider_settings(
    settings: Settings,
    *,
    model_name: str,
    model_setting_name: str,
) -> None:
    if not settings.public_llm_enabled:
        raise ModelProviderConfigurationError("Public LLM providers require PUBLIC_LLM_ENABLED=true.")
    if not settings.public_llm_api_key.strip():
        raise ModelProviderConfigurationError("Public LLM providers require PUBLIC_LLM_API_KEY.")
    if not model_name.strip():
        raise ModelProviderConfigurationError(f"Public LLM providers require {model_setting_name}.")


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


def _ollama_embedding_from_response(data: dict) -> list[float]:
    if isinstance(data.get("embeddings"), list) and data["embeddings"]:
        embedding = data["embeddings"][0]
    else:
        embedding = data.get("embedding")

    if not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding):
        raise ModelProviderRequestError("Ollama embedding response did not include a numeric vector.")
    return [float(value) for value in embedding]


def _openai_embedding_from_response(data: dict, *, provider: str = "vLLM") -> list[float]:
    items = data.get("data")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ModelProviderRequestError(
            f"{provider} embedding response did not include data[0].embedding."
        )
    embedding = items[0].get("embedding")
    if not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding):
        raise ModelProviderRequestError(f"{provider} embedding response did not include a numeric vector.")
    return [float(value) for value in embedding]


def _openai_chat_answer_from_response(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"].strip()
    text = choices[0].get("text")
    return text.strip() if isinstance(text, str) else ""


def _post_ollama_json(
    client: httpx.Client,
    endpoint: str,
    payload: dict,
    model_name: str,
    base_url: str,
    operation: str,
) -> httpx.Response:
    return _post_json(
        client=client,
        endpoint=endpoint,
        payload=payload,
        provider="Ollama",
        model_name=model_name,
        base_url=base_url,
        operation=operation,
    )


def _post_json(
    client: httpx.Client,
    endpoint: str,
    payload: dict,
    provider: str,
    model_name: str,
    base_url: str,
    operation: str,
) -> httpx.Response:
    try:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        response.json()
    except httpx.TimeoutException as exc:
        raise ModelProviderRequestError(
            f"{provider} {operation} timed out for model '{model_name}' at {base_url}{endpoint}."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = _provider_error_detail(exc.response)
        raise ModelProviderRequestError(
            f"{provider} {operation} failed for model '{model_name}' at {base_url}{endpoint} "
            f"with HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ModelProviderRequestError(
            f"{provider} {operation} request failed for model '{model_name}' at {base_url}{endpoint}: "
            f"{exc.__class__.__name__}."
        ) from exc
    except (JSONDecodeError, ValueError) as exc:
        raise ModelProviderRequestError(
            f"{provider} {operation} response for model '{model_name}' was not valid JSON."
        ) from exc
    return response


def _authorization_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _provider_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except (JSONDecodeError, ValueError):
        return response.text[:240] or "no response body"
    if isinstance(data, dict):
        detail = data.get("error") or data.get("detail") or data.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()[:240]
    return response.text[:240] or "no response body"


def _normalize_embedding(embedding: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in embedding))
    if norm == 0:
        return embedding
    return [value / norm for value in embedding]


def _answer_prompt(query: str, results: list[RetrievalResult]) -> str:
    context_blocks = []
    for index, result in enumerate(results, start=1):
        metadata = result.chunk.metadata
        source = metadata.get("file_name") or metadata.get("document_id") or "authorized context"
        context_blocks.append(f"[{index}] Source: {source}\n{result.chunk.text.strip()}")

    context = "\n\n".join(context_blocks)
    return (
        "Answer the question using only the authorized context below. "
        "If the context does not contain enough evidence, say that you do not have enough authorized context. "
        "Keep the answer concise and do not invent sources.\n\n"
        f"Question: {query}\n\n"
        f"Authorized context:\n{context}\n\n"
        "Answer:"
    )
