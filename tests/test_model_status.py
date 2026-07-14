import httpx

from app.config import Settings
import app.rag.model_status as model_status_module
from app.rag.model_status import get_model_status


def test_default_model_status_reports_ready_local_runtimes() -> None:
    status = get_model_status(Settings(_env_file=None))

    assert status.model_profile == "custom"
    assert status.gpu_profile == "none"
    assert status.llm_provider == "local"
    assert status.embedding.runtime == "hashing"
    assert status.embedding.ready is True
    assert status.answer.runtime == "extractive"
    assert status.answer.ready is True
    assert status.vector_index.runtime == "memory"
    assert status.vector_index.ready is True
    assert status.reranker.runtime == "none"
    assert status.reranker.ready is True
    assert status.performance.retrieval_warning_ms == 1500.0


def test_ollama_status_reports_ready_when_model_is_installed(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"models": [{"name": "nomic-embed-text:latest"}]},
                )
            ),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            local_embedding_runtime="ollama",
            local_embedding_model_name="nomic-embed-text:latest",
            local_embedding_base_url="http://ollama.test",
        )
    )

    assert status.embedding.ready is True
    assert status.embedding.base_url == "http://ollama.test"
    assert "configured model is installed" in status.embedding.message


def test_qdrant_status_reports_collection_readiness(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"result": {}})),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            vector_index_backend="qdrant",
            qdrant_url="http://qdrant.test",
            qdrant_collection_name="rag_chunks",
        )
    )

    assert status.vector_index.ready is True
    assert status.vector_index.base_url == "http://qdrant.test"
    assert "collection exists" in status.vector_index.message


def test_vllm_runtime_reports_ready_when_health_endpoint_is_ready(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "ok"})),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            local_embedding_runtime="vllm",
            local_embedding_model_name="BAAI/bge-small-en-v1.5",
            local_embedding_base_url="http://vllm.test",
            local_llm_runtime="vllm",
            local_llm_model_name="mistralai/Mistral-7B-Instruct-v0.3",
            local_llm_base_url="http://vllm.test",
        )
    )

    assert status.embedding.ready is True
    assert status.embedding.runtime == "vllm"
    assert status.answer.ready is True
    assert status.answer.runtime == "vllm"


def test_local_cross_encoder_reranker_reports_ready_when_health_endpoint_is_ready(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "ok"})),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            reranker_provider="local",
            local_reranker_runtime="cross-encoder",
            local_reranker_model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
            local_reranker_base_url="http://reranker.test",
        )
    )

    assert status.reranker.ready is True
    assert status.reranker.runtime == "cross-encoder"
    assert status.reranker.base_url == "http://reranker.test"


def test_ollama_status_accepts_model_field_from_tags(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"models": [{"model": "llama3.1:8b"}]},
                )
            ),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            local_llm_runtime="ollama",
            local_llm_model_name="llama3.1:8b",
            local_llm_base_url="http://ollama.test",
        )
    )

    assert status.answer.ready is True


def test_ollama_status_reports_not_ready_when_model_is_missing(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})
            ),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            local_embedding_runtime="ollama",
            local_embedding_model_name="nomic-embed-text:latest",
            local_embedding_base_url="http://ollama.test",
        )
    )

    assert status.embedding.ready is False
    assert "configured model is not installed" in status.embedding.message


def test_ollama_status_reports_not_ready_for_invalid_tags_json(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"nope")),
        ),
    )

    status = get_model_status(
        Settings(
            _env_file=None,
            local_embedding_runtime="ollama",
            local_embedding_model_name="nomic-embed-text:latest",
            local_embedding_base_url="http://ollama.test",
        )
    )

    assert status.embedding.ready is False
    assert "valid JSON" in status.embedding.message


def test_model_status_endpoint_returns_authenticated_runtime_status(api_client_as, monkeypatch) -> None:
    monkeypatch.setattr(model_status_module, "get_settings", lambda: Settings(_env_file=None))
    client = api_client_as("00000000-0000-4000-8000-000000000009", ["admin"])

    response = client.get("/api/v1/model-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding"]["runtime"] == "hashing"
    assert payload["embedding"]["ready"] is True


def test_model_status_reports_resolved_model_profile(monkeypatch) -> None:
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": "nomic-embed-text:latest"},
                            {"name": "llama3.1:8b"},
                        ]
                    },
                )
            ),
        ),
    )

    status = get_model_status(Settings(_env_file=None, local_model_profile="host-ollama"))

    assert status.model_profile == "host-ollama"
    assert status.embedding.runtime == "ollama"
    assert status.embedding.base_url == "http://host.docker.internal:11434"
    assert status.answer.runtime == "ollama"
    assert status.answer.base_url == "http://host.docker.internal:11434"
