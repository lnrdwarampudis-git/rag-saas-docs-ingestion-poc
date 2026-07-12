import httpx

from app.config import Settings, get_settings
from app.schemas.model_status import ModelRuntimeStatus, ModelStatusResponse


SUPPORTED_EMBEDDING_RUNTIMES = {"hashing", "ollama"}
SUPPORTED_ANSWER_RUNTIMES = {"extractive", "ollama"}


def get_model_status(settings: Settings | None = None) -> ModelStatusResponse:
    settings = settings or get_settings()
    llm_provider = settings.llm_provider.lower()
    embedding_provider = settings.embedding_provider.lower()
    embedding_runtime = settings.local_embedding_runtime.lower()
    answer_runtime = settings.local_llm_runtime.lower()

    return ModelStatusResponse(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        embedding=_embedding_status(settings, embedding_provider, embedding_runtime),
        answer=_answer_status(settings, llm_provider, answer_runtime),
    )


def _embedding_status(
    settings: Settings,
    embedding_provider: str,
    runtime: str,
) -> ModelRuntimeStatus:
    if embedding_provider != "local":
        return ModelRuntimeStatus(
            provider=embedding_provider,
            runtime=runtime,
            model_name=settings.local_embedding_model_name,
            ready=False,
            message="Unsupported embedding provider.",
        )
    if runtime == "hashing":
        return ModelRuntimeStatus(
            provider=embedding_provider,
            runtime=runtime,
            model_name=settings.local_embedding_model_name,
            ready=True,
            message="In-process hashing embeddings are ready.",
        )
    if runtime == "ollama":
        return _ollama_status(
            provider=embedding_provider,
            runtime=runtime,
            model_name=settings.local_embedding_model_name,
            base_url=settings.local_embedding_base_url,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    return _unsupported_runtime_status(
        provider=embedding_provider,
        runtime=runtime,
        model_name=settings.local_embedding_model_name,
        supported_runtimes=SUPPORTED_EMBEDDING_RUNTIMES,
    )


def _answer_status(settings: Settings, llm_provider: str, runtime: str) -> ModelRuntimeStatus:
    if llm_provider != "local":
        return ModelRuntimeStatus(
            provider=llm_provider,
            runtime=runtime,
            model_name=settings.local_llm_model_name,
            ready=settings.public_llm_enabled,
            message=(
                "Public LLM provider is enabled."
                if settings.public_llm_enabled
                else "Public LLM providers require PUBLIC_LLM_ENABLED=true."
            ),
        )
    if runtime == "extractive":
        return ModelRuntimeStatus(
            provider=llm_provider,
            runtime=runtime,
            model_name=settings.local_llm_model_name,
            ready=True,
            message="Extractive answer generation is ready.",
        )
    if runtime == "ollama":
        return _ollama_status(
            provider=llm_provider,
            runtime=runtime,
            model_name=settings.local_llm_model_name,
            base_url=settings.local_llm_base_url,
            timeout_seconds=settings.local_model_request_timeout_seconds,
        )
    return _unsupported_runtime_status(
        provider=llm_provider,
        runtime=runtime,
        model_name=settings.local_llm_model_name,
        supported_runtimes=SUPPORTED_ANSWER_RUNTIMES,
    )


def _ollama_status(
    provider: str,
    runtime: str,
    model_name: str,
    base_url: str,
    timeout_seconds: float,
) -> ModelRuntimeStatus:
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=min(timeout_seconds, 5.0)) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            models = _ollama_model_names(response.json())
    except httpx.HTTPError as exc:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message=f"Ollama is not reachable: {exc.__class__.__name__}.",
            base_url=base_url,
        )

    if model_name in models:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=True,
            message="Ollama is reachable and the configured model is installed.",
            base_url=base_url,
        )

    return ModelRuntimeStatus(
        provider=provider,
        runtime=runtime,
        model_name=model_name,
        ready=False,
        message="Ollama is reachable, but the configured model is not installed.",
        base_url=base_url,
    )


def _ollama_model_names(payload: dict) -> set[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return set()
    names = {
        model.get("name")
        for model in models
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    return {name for name in names if name}


def _unsupported_runtime_status(
    provider: str,
    runtime: str,
    model_name: str,
    supported_runtimes: set[str],
) -> ModelRuntimeStatus:
    supported = ", ".join(sorted(supported_runtimes))
    return ModelRuntimeStatus(
        provider=provider,
        runtime=runtime,
        model_name=model_name,
        ready=False,
        message=f"Unsupported runtime. Supported runtimes: {supported}.",
    )

