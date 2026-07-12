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
    chunk_target_tokens: int = 750
    chunk_overlap_tokens: int = 120
    upload_dir: str = "/tmp/rag-uploads"
    enable_db_persistence: bool = False
    host_mount_source_prefix: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
