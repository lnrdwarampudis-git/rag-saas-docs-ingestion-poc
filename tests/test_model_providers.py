import pytest
import httpx

from app.config import Settings
from app.rag.embeddings import HashingEmbeddingModel
from app.rag.model_providers import (
    ExtractiveAnswerGenerator,
    ModelProviderConfigurationError,
    ModelProviderRequestError,
    OllamaAnswerGenerator,
    OllamaEmbeddingModel,
    VllmAnswerGenerator,
    VllmEmbeddingModel,
    build_model_provider,
)
from app.rag.retrieval import RetrievalResult
from app.schemas.documents import ChunkDTO


def test_default_model_provider_uses_local_hashing_and_extractive_runtime() -> None:
    provider = build_model_provider(Settings(_env_file=None))

    assert provider.provider_name == "local"
    assert provider.embedding_provider == "local"
    assert provider.embedding_runtime == "hashing"
    assert provider.answer_runtime == "extractive"
    assert isinstance(provider.embedding_model, HashingEmbeddingModel)
    assert isinstance(provider.answer_generator, ExtractiveAnswerGenerator)


def test_local_embedding_dimensions_are_configurable() -> None:
    provider = build_model_provider(Settings(_env_file=None, embedding_dimensions=16))

    assert len(provider.embedding_model.embed("Redis vector retrieval")) == 16


def test_public_llm_provider_requires_explicit_enablement() -> None:
    with pytest.raises(ModelProviderConfigurationError, match="PUBLIC_LLM_ENABLED"):
        build_model_provider(
            Settings(_env_file=None, llm_provider="openai", public_llm_enabled=False)
        )


def test_ollama_embedding_runtime_is_available() -> None:
    provider = build_model_provider(
        Settings(
            _env_file=None,
            local_embedding_runtime="ollama",
            local_embedding_model_name="nomic-embed-text",
            local_embedding_base_url="http://ollama:11434",
        )
    )

    assert provider.embedding_runtime == "ollama"
    assert provider.embedding_model_name == "nomic-embed-text"
    assert isinstance(provider.embedding_model, OllamaEmbeddingModel)


def test_ollama_embedding_model_posts_to_local_embed_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[3, 4]]})

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    model = OllamaEmbeddingModel(
        base_url="http://ollama.test",
        model_name="nomic-embed-text",
        client=client,
    )

    embedding = model.embed("Redis vector retrieval")

    assert requests[0].url.path == "/api/embed"
    assert requests[0].read() == (
        b'{"model":"nomic-embed-text","input":"Redis vector retrieval"}'
    )
    assert embedding == [0.6, 0.8]


def test_ollama_embedding_model_rejects_invalid_response_shape() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"done": True})),
    )
    model = OllamaEmbeddingModel(
        base_url="http://ollama.test",
        model_name="nomic-embed-text",
        client=client,
    )

    with pytest.raises(ModelProviderRequestError, match="numeric vector"):
        model.embed("Redis vector retrieval")


def test_ollama_embedding_model_reports_http_status_detail() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"error": "model not found"})
        ),
    )
    model = OllamaEmbeddingModel(
        base_url="http://ollama.test",
        model_name="missing-embed",
        client=client,
    )

    with pytest.raises(ModelProviderRequestError) as exc:
        model.embed("Redis vector retrieval")

    message = str(exc.value)
    assert "HTTP 404" in message
    assert "model not found" in message
    assert "missing-embed" in message


def test_ollama_embedding_model_reports_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow model", request=request)

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    model = OllamaEmbeddingModel(
        base_url="http://ollama.test",
        model_name="nomic-embed-text",
        client=client,
    )

    with pytest.raises(ModelProviderRequestError, match="timed out"):
        model.embed("Redis vector retrieval")


def test_ollama_answer_runtime_is_available() -> None:
    provider = build_model_provider(
        Settings(
            _env_file=None,
            local_llm_runtime="ollama",
            local_llm_model_name="llama3.1",
            local_llm_base_url="http://ollama:11434",
        )
    )

    assert provider.answer_runtime == "ollama"
    assert provider.answer_model_name == "llama3.1"
    assert isinstance(provider.answer_generator, OllamaAnswerGenerator)


def test_ollama_answer_generator_posts_authorized_context() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": "Redis lowers repeated query latency."})

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    generator = OllamaAnswerGenerator(
        base_url="http://ollama.test",
        model_name="llama3.1",
        client=client,
    )

    answer = generator.generate(
        "How does Redis help?",
        [
            RetrievalResult(
                chunk=ChunkDTO(
                    chunk_index=0,
                    text="Redis cache improves repeated RAG query latency.",
                    token_count=7,
                    metadata={"file_name": "architecture.md"},
                ),
                score=1.0,
                keyword_score=1.0,
                vector_score=1.0,
                early_score=1.0,
            )
        ],
    )

    payload = _request_json(requests[0])
    assert requests[0].url.path == "/api/generate"
    assert payload["model"] == "llama3.1"
    assert payload["stream"] is False
    assert "How does Redis help?" in payload["prompt"]
    assert "Redis cache improves repeated RAG query latency." in payload["prompt"]
    assert answer == "Redis lowers repeated query latency."


def test_ollama_answer_generator_rejects_invalid_response_shape() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"done": True})),
    )
    generator = OllamaAnswerGenerator(
        base_url="http://ollama.test",
        model_name="llama3.1",
        client=client,
    )

    with pytest.raises(ModelProviderRequestError, match="answer text"):
        generator.generate(
            "How does Redis help?",
            [
                RetrievalResult(
                    chunk=ChunkDTO(
                        chunk_index=0,
                        text="Redis cache improves repeated RAG query latency.",
                        token_count=7,
                        metadata={"file_name": "architecture.md"},
                    ),
                    score=1.0,
                    keyword_score=1.0,
                    vector_score=1.0,
                    early_score=1.0,
                )
            ],
        )


def test_ollama_answer_generator_reports_invalid_json() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"not-json")
        ),
    )
    generator = OllamaAnswerGenerator(
        base_url="http://ollama.test",
        model_name="llama3.1",
        client=client,
    )

    with pytest.raises(ModelProviderRequestError, match="not valid JSON"):
        generator.generate(
            "How does Redis help?",
            [
                RetrievalResult(
                    chunk=ChunkDTO(
                        chunk_index=0,
                        text="Redis cache improves repeated RAG query latency.",
                        token_count=7,
                        metadata={"file_name": "architecture.md"},
                    ),
                    score=1.0,
                    keyword_score=1.0,
                    vector_score=1.0,
                    early_score=1.0,
                )
            ],
        )


def test_vllm_embedding_runtime_is_available() -> None:
    provider = build_model_provider(
        Settings(
            _env_file=None,
            local_embedding_runtime="vllm",
            local_embedding_model_name="BAAI/bge-small-en-v1.5",
            local_embedding_base_url="http://vllm:8000",
        )
    )

    assert provider.embedding_runtime == "vllm"
    assert isinstance(provider.embedding_model, VllmEmbeddingModel)


def test_vllm_embedding_model_posts_to_openai_compatible_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [{"embedding": [5, 12]}]})

    client = httpx.Client(
        base_url="http://vllm.test",
        transport=httpx.MockTransport(handler),
    )
    model = VllmEmbeddingModel(
        base_url="http://vllm.test",
        model_name="BAAI/bge-small-en-v1.5",
        client=client,
    )

    embedding = model.embed("Redis vector retrieval")

    assert requests[0].url.path == "/v1/embeddings"
    assert _request_json(requests[0]) == {
        "model": "BAAI/bge-small-en-v1.5",
        "input": "Redis vector retrieval",
    }
    assert embedding == [5 / 13, 12 / 13]


def test_vllm_generation_runtime_is_available() -> None:
    provider = build_model_provider(
        Settings(
            _env_file=None,
            local_llm_runtime="vllm",
            local_llm_model_name="mistralai/Mistral-7B-Instruct-v0.3",
            local_llm_base_url="http://vllm:8000",
        )
    )

    assert provider.answer_runtime == "vllm"
    assert isinstance(provider.answer_generator, VllmAnswerGenerator)


def test_vllm_answer_generator_posts_chat_completion() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Redis lowers repeated query latency."}}]},
        )

    client = httpx.Client(
        base_url="http://vllm.test",
        transport=httpx.MockTransport(handler),
    )
    generator = VllmAnswerGenerator(
        base_url="http://vllm.test",
        model_name="mistralai/Mistral-7B-Instruct-v0.3",
        client=client,
    )

    answer = generator.generate(
        "How does Redis help?",
        [
            RetrievalResult(
                chunk=ChunkDTO(
                    chunk_index=0,
                    text="Redis cache improves repeated RAG query latency.",
                    token_count=7,
                    metadata={"file_name": "architecture.md"},
                ),
                score=1.0,
                keyword_score=1.0,
                vector_score=1.0,
                early_score=1.0,
            )
        ],
    )

    payload = _request_json(requests[0])
    assert requests[0].url.path == "/v1/chat/completions"
    assert payload["model"] == "mistralai/Mistral-7B-Instruct-v0.3"
    assert payload["temperature"] == 0
    assert answer == "Redis lowers repeated query latency."


def _request_json(request: httpx.Request) -> dict:
    import json

    return json.loads(request.read().decode("utf-8"))
