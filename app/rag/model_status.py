from json import JSONDecodeError

import httpx

from app.config import Settings, get_settings
from app.rag.model_profiles import resolve_model_profile
from app.schemas.model_status import ModelPerformanceStatus, ModelRuntimeStatus, ModelStatusResponse


SUPPORTED_EMBEDDING_RUNTIMES = {"hashing", "ollama", "vllm"}
SUPPORTED_ANSWER_RUNTIMES = {"extractive", "ollama", "vllm"}
SUPPORTED_PUBLIC_PROVIDERS = {"openai"}
SUPPORTED_RERANKER_RUNTIMES = {"none", "keyword", "cross-encoder", "vllm"}


def get_model_status(settings: Settings | None = None) -> ModelStatusResponse:
    settings = resolve_model_profile(settings or get_settings())
    llm_provider = settings.llm_provider.lower()
    embedding_provider = settings.embedding_provider.lower()
    embedding_runtime = settings.local_embedding_runtime.lower()
    answer_runtime = settings.local_llm_runtime.lower()

    return ModelStatusResponse(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        model_profile=settings.local_model_profile,
        gpu_profile=settings.local_model_gpu_profile,
        embedding=_embedding_status(settings, embedding_provider, embedding_runtime),
        answer=_answer_status(settings, llm_provider, answer_runtime),
        vector_index=_vector_index_status(settings),
        reranker=_reranker_status(settings),
        performance=ModelPerformanceStatus(
            retrieval_warning_ms=settings.retrieval_latency_warning_ms,
            total_warning_ms=settings.total_latency_warning_ms,
        ),
    )


def _embedding_status(
    settings: Settings,
    embedding_provider: str,
    runtime: str,
) -> ModelRuntimeStatus:
    if embedding_provider != "local":
        return _public_provider_status(
            settings,
            provider=embedding_provider,
            runtime="openai-compatible",
            model_name=settings.public_embedding_model_name,
            model_setting_name="PUBLIC_EMBEDDING_MODEL_NAME",
            component="embedding",
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
    if runtime == "vllm":
        return _http_health_status(
            provider=embedding_provider,
            runtime=runtime,
            model_name=settings.local_embedding_model_name,
            base_url=settings.local_embedding_base_url,
            timeout_seconds=settings.local_model_request_timeout_seconds,
            ready_message="vLLM-compatible embedding endpoint is reachable.",
            attention_message="vLLM-compatible embedding endpoint health check needs attention",
        )
    return _unsupported_runtime_status(
        provider=embedding_provider,
        runtime=runtime,
        model_name=settings.local_embedding_model_name,
        supported_runtimes=SUPPORTED_EMBEDDING_RUNTIMES,
    )


def _answer_status(settings: Settings, llm_provider: str, runtime: str) -> ModelRuntimeStatus:
    if llm_provider != "local":
        return _public_provider_status(
            settings,
            provider=llm_provider,
            runtime="openai-compatible",
            model_name=settings.public_llm_model_name,
            model_setting_name="PUBLIC_LLM_MODEL_NAME",
            component="answer generation",
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
    if runtime == "vllm":
        return _http_health_status(
            provider=llm_provider,
            runtime=runtime,
            model_name=settings.local_llm_model_name,
            base_url=settings.local_llm_base_url,
            timeout_seconds=settings.local_model_request_timeout_seconds,
            ready_message="vLLM-compatible generation endpoint is reachable.",
            attention_message="vLLM-compatible generation endpoint health check needs attention",
        )
    return _unsupported_runtime_status(
        provider=llm_provider,
        runtime=runtime,
        model_name=settings.local_llm_model_name,
        supported_runtimes=SUPPORTED_ANSWER_RUNTIMES,
    )


def _public_provider_status(
    settings: Settings,
    *,
    provider: str,
    runtime: str,
    model_name: str,
    model_setting_name: str,
    component: str,
) -> ModelRuntimeStatus:
    if provider not in SUPPORTED_PUBLIC_PROVIDERS:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message=f"Unsupported public provider. Supported public providers: {', '.join(sorted(SUPPORTED_PUBLIC_PROVIDERS))}.",
            base_url=settings.public_llm_base_url,
        )
    if not settings.public_llm_enabled:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message="Public LLM providers require PUBLIC_LLM_ENABLED=true.",
            base_url=settings.public_llm_base_url,
        )
    if not settings.public_llm_api_key.strip():
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message="Public LLM providers require PUBLIC_LLM_API_KEY.",
            base_url=settings.public_llm_base_url,
        )
    if not model_name.strip():
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message=f"Public LLM providers require {model_setting_name}.",
            base_url=settings.public_llm_base_url,
        )
    return ModelRuntimeStatus(
        provider=provider,
        runtime=runtime,
        model_name=model_name,
        ready=True,
        message=f"Public {component} provider is configured. Readiness does not call the external API.",
        base_url=settings.public_llm_base_url,
    )


def _vector_index_status(settings: Settings) -> ModelRuntimeStatus:
    backend = settings.vector_index_backend.lower()
    if backend == "memory":
        return ModelRuntimeStatus(
            provider="local",
            runtime=backend,
            model_name="in-process",
            ready=True,
            message="In-memory vector index is ready for local deterministic runs.",
        )
    if backend == "pgvector":
        return ModelRuntimeStatus(
            provider="postgres",
            runtime=backend,
            model_name=f"{settings.pgvector_dimensions}d",
            ready=settings.enable_db_persistence,
            message=(
                "pgvector retrieval is configured with database persistence enabled."
                if settings.enable_db_persistence
                else "pgvector retrieval requires ENABLE_DB_PERSISTENCE=true."
            ),
        )
    if backend == "qdrant":
        return _qdrant_status(settings)
    return ModelRuntimeStatus(
        provider="vector-index",
        runtime=backend,
        model_name="unknown",
        ready=False,
        message="Unsupported vector index backend. Supported backends: memory, pgvector, qdrant.",
    )


def _qdrant_status(settings: Settings) -> ModelRuntimeStatus:
    try:
        with httpx.Client(
            base_url=settings.qdrant_url.rstrip("/"),
            timeout=min(settings.qdrant_request_timeout_seconds, 5.0),
        ) as client:
            response = client.get(f"/collections/{settings.qdrant_collection_name}")
    except httpx.HTTPError as exc:
        return ModelRuntimeStatus(
            provider="qdrant",
            runtime="qdrant",
            model_name=settings.qdrant_collection_name,
            ready=False,
            message=f"Qdrant is not reachable: {exc.__class__.__name__}.",
            base_url=settings.qdrant_url,
        )

    if response.status_code == 200:
        return ModelRuntimeStatus(
            provider="qdrant",
            runtime="qdrant",
            model_name=settings.qdrant_collection_name,
            ready=True,
            message="Qdrant is reachable and the configured collection exists.",
            base_url=settings.qdrant_url,
        )
    if response.status_code == 404:
        return ModelRuntimeStatus(
            provider="qdrant",
            runtime="qdrant",
            model_name=settings.qdrant_collection_name,
            ready=False,
            message="Qdrant is reachable, but the collection has not been created or backfilled yet.",
            base_url=settings.qdrant_url,
        )
    return ModelRuntimeStatus(
        provider="qdrant",
        runtime="qdrant",
        model_name=settings.qdrant_collection_name,
        ready=False,
        message=f"Qdrant collection check returned HTTP {response.status_code}.",
        base_url=settings.qdrant_url,
    )


def _reranker_status(settings: Settings) -> ModelRuntimeStatus:
    provider = settings.reranker_provider.lower()
    runtime = settings.local_reranker_runtime.lower()
    if provider == "none" or runtime == "none":
        return ModelRuntimeStatus(
            provider=provider,
            runtime="none",
            model_name=settings.local_reranker_model_name,
            ready=True,
            message="Reranking is disabled; hybrid retrieval ranking is active.",
        )
    if provider == "local" and runtime == "keyword":
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=settings.local_reranker_model_name,
            ready=True,
            message="Deterministic local keyword reranker is ready.",
        )
    if provider == "local" and runtime in {"cross-encoder", "vllm"}:
        return _http_health_status(
            provider=provider,
            runtime=runtime,
            model_name=settings.local_reranker_model_name,
            base_url=settings.local_reranker_base_url,
            timeout_seconds=settings.local_reranker_request_timeout_seconds,
            ready_message=f"Local {runtime} reranker endpoint is reachable.",
            attention_message=f"Local {runtime} reranker endpoint health check needs attention",
        )
    return _unsupported_runtime_status(
        provider=provider,
        runtime=runtime,
        model_name=settings.local_reranker_model_name,
        supported_runtimes=SUPPORTED_RERANKER_RUNTIMES,
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
    except (JSONDecodeError, ValueError):
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message="Ollama is reachable, but /api/tags did not return valid JSON.",
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


def _http_health_status(
    *,
    provider: str,
    runtime: str,
    model_name: str,
    base_url: str,
    timeout_seconds: float,
    ready_message: str,
    attention_message: str,
) -> ModelRuntimeStatus:
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=min(timeout_seconds, 5.0)) as client:
            response = client.get("/health")
    except httpx.HTTPError as exc:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=False,
            message=f"{attention_message}: {exc.__class__.__name__}.",
            base_url=base_url,
        )

    if response.status_code < 400:
        return ModelRuntimeStatus(
            provider=provider,
            runtime=runtime,
            model_name=model_name,
            ready=True,
            message=ready_message,
            base_url=base_url,
        )
    return ModelRuntimeStatus(
        provider=provider,
        runtime=runtime,
        model_name=model_name,
        ready=False,
        message=f"{attention_message}: HTTP {response.status_code}.",
        base_url=base_url,
    )


def _ollama_model_names(payload: dict) -> set[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return set()
    names = {
        model.get("name") or model.get("model")
        for model in models
        if isinstance(model, dict)
        and isinstance(model.get("name") or model.get("model"), str)
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
