from app.config import Settings


MODEL_PROFILES: dict[str, dict[str, str]] = {
    "local-default": {
        "local_embedding_runtime": "hashing",
        "local_embedding_model_name": "hashing-384",
        "local_llm_runtime": "extractive",
        "local_llm_model_name": "extractive",
        "reranker_provider": "none",
        "local_reranker_runtime": "none",
        "local_reranker_model_name": "none",
    },
    "host-ollama": {
        "local_embedding_runtime": "ollama",
        "local_embedding_model_name": "nomic-embed-text:latest",
        "local_embedding_base_url": "http://host.docker.internal:11434",
        "local_llm_runtime": "ollama",
        "local_llm_model_name": "llama3.1:8b",
        "local_llm_base_url": "http://host.docker.internal:11434",
    },
    "compose-ollama": {
        "local_embedding_runtime": "ollama",
        "local_embedding_model_name": "nomic-embed-text",
        "local_embedding_base_url": "http://ollama:11434",
        "local_llm_runtime": "ollama",
        "local_llm_model_name": "llama3.1",
        "local_llm_base_url": "http://ollama:11434",
    },
    "vllm-gpu": {
        "local_embedding_runtime": "vllm",
        "local_embedding_model_name": "BAAI/bge-small-en-v1.5",
        "local_embedding_base_url": "http://host.docker.internal:8000",
        "local_llm_runtime": "vllm",
        "local_llm_model_name": "mistralai/Mistral-7B-Instruct-v0.3",
        "local_llm_base_url": "http://host.docker.internal:8000",
        "reranker_provider": "local",
        "local_reranker_runtime": "cross-encoder",
        "local_reranker_model_name": "BAAI/bge-reranker-base",
        "local_reranker_base_url": "http://host.docker.internal:8081",
    },
}


def resolve_model_profile(settings: Settings) -> Settings:
    profile = settings.local_model_profile.lower()
    if profile in {"", "custom"}:
        return settings
    updates = MODEL_PROFILES.get(profile)
    if updates is None:
        return settings
    return settings.model_copy(update=updates)
