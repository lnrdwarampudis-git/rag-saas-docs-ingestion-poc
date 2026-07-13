from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "rag-saas-docs-ingestion-poc"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    qdrant_url: str = "http://localhost:6333"
    keycloak_issuer: str = "http://localhost:8080/realms/rag"
    keycloak_audience: str = "rag-api"
    keycloak_client_id: str = "rag-frontend"
    keycloak_internal_issuer: str = "http://localhost:8080/realms/rag"
    keycloak_jwks_cache_seconds: int = 300
    chunk_target_tokens: int = 750
    chunk_overlap_tokens: int = 120
    upload_dir: str = "/tmp/rag-uploads"
    max_upload_bytes: int = 536_870_912
    allowed_upload_extensions: str = ".pdf,.txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.bmp"
    enable_db_persistence: bool = False
    host_mount_source_prefix: str = ""
    retrieval_min_score: float = 0.12
    retrieval_min_keyword_overlap: float = 0.20
    llm_provider: str = "local"
    local_llm_runtime: str = "extractive"
    local_llm_model_name: str = "extractive"
    local_llm_base_url: str = "http://localhost:11434"
    embedding_provider: str = "local"
    local_embedding_runtime: str = "hashing"
    local_embedding_model_name: str = "hashing-384"
    embedding_dimensions: int = 384
    local_embedding_base_url: str = "http://localhost:11434"
    local_model_request_timeout_seconds: float = 30.0
    public_llm_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
