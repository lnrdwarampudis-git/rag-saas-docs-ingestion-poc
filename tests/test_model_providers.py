import pytest

from app.config import Settings
from app.rag.embeddings import HashingEmbeddingModel
from app.rag.model_providers import (
    ExtractiveAnswerGenerator,
    ModelProviderConfigurationError,
    build_model_provider,
)


def test_default_model_provider_uses_local_hashing_and_extractive_runtime() -> None:
    provider = build_model_provider(Settings())

    assert provider.provider_name == "local"
    assert provider.embedding_provider == "local"
    assert provider.embedding_runtime == "hashing"
    assert provider.answer_runtime == "extractive"
    assert isinstance(provider.embedding_model, HashingEmbeddingModel)
    assert isinstance(provider.answer_generator, ExtractiveAnswerGenerator)


def test_local_embedding_dimensions_are_configurable() -> None:
    provider = build_model_provider(Settings(embedding_dimensions=16))

    assert len(provider.embedding_model.embed("Redis vector retrieval")) == 16


def test_public_llm_provider_requires_explicit_enablement() -> None:
    with pytest.raises(ModelProviderConfigurationError, match="PUBLIC_LLM_ENABLED"):
        build_model_provider(Settings(llm_provider="openai", public_llm_enabled=False))


def test_future_local_runtimes_are_reserved_until_adapter_is_implemented() -> None:
    with pytest.raises(ModelProviderConfigurationError, match="future adapter"):
        build_model_provider(Settings(local_llm_runtime="ollama"))

    with pytest.raises(ModelProviderConfigurationError, match="future adapter"):
        build_model_provider(Settings(local_embedding_runtime="vllm"))
