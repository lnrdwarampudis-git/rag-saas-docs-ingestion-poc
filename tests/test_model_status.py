import httpx

from app.config import Settings
import app.rag.model_status as model_status_module
from app.rag.model_status import get_model_status


def test_default_model_status_reports_ready_local_runtimes() -> None:
    status = get_model_status(Settings(_env_file=None))

    assert status.llm_provider == "local"
    assert status.embedding.runtime == "hashing"
    assert status.embedding.ready is True
    assert status.answer.runtime == "extractive"
    assert status.answer.ready is True


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


def test_model_status_endpoint_returns_authenticated_runtime_status(api_client_as, monkeypatch) -> None:
    monkeypatch.setattr(model_status_module, "get_settings", lambda: Settings(_env_file=None))
    client = api_client_as("00000000-0000-4000-8000-000000000009", ["admin"])

    response = client.get("/api/v1/model-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding"]["runtime"] == "hashing"
    assert payload["embedding"]["ready"] is True
    assert payload["answer"]["runtime"] == "extractive"
    assert payload["answer"]["ready"] is True
