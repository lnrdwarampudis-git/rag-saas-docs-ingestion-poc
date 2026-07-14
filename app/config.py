from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "rag-saas-docs-ingestion-poc"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"
    processing_queue_name: str = "rag:processing-jobs"
    ocr_processing_queue_name: str = "rag:processing-jobs:ocr"
    worker_queue_names: str = "rag:processing-jobs,rag:processing-jobs:ocr"
    worker_max_jobs_per_run: int = 0
    processing_dead_letter_queue_name: str = "rag:processing-jobs:dead-letter"
    processing_job_max_attempts: int = 3
    minio_endpoint: str = "http://localhost:9000"
    minio_public_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"
    minio_secure: bool = False
    upload_session_storage_backend: str = "filesystem"
    upload_session_bucket: str = "rag-upload-sessions"
    upload_session_presign_expiry_seconds: int = 3600
    upload_session_cleanup_max_age_hours: int = 24
    upload_session_lifecycle_expiration_days: int = 7
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "rag_chunks"
    qdrant_request_timeout_seconds: float = 10.0
    keycloak_issuer: str = "http://localhost:8080/realms/rag"
    keycloak_audience: str = "rag-api"
    keycloak_client_id: str = "rag-frontend"
    keycloak_internal_issuer: str = "http://localhost:8080/realms/rag"
    keycloak_jwks_cache_seconds: int = 300
    chunk_target_tokens: int = 750
    chunk_overlap_tokens: int = 120
    upload_dir: str = "/tmp/rag-uploads"
    max_upload_bytes: int = 536_870_912
    upload_session_part_bytes: int = 8_388_608
    upload_session_max_parts: int = 10_000
    allowed_upload_extensions: str = ".pdf,.txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.bmp"
    ocr_language: str = "eng"
    ocr_pdf_dpi: int = 200
    ocr_max_pdf_pages: int = 20
    enable_db_persistence: bool = False
    host_mount_source_prefix: str = ""
    retrieval_min_score: float = 0.12
    retrieval_min_keyword_overlap: float = 0.20
    vector_index_backend: str = "memory"
    pgvector_dimensions: int = 1024
    vector_backfill_batch_size: int = 100
    reranker_provider: str = "none"
    local_reranker_runtime: str = "none"
    local_reranker_model_name: str = "none"
    local_reranker_base_url: str = "http://localhost:8081"
    local_reranker_request_timeout_seconds: float = 30.0
    reranker_candidate_multiplier: int = 4
    retrieval_latency_warning_ms: float = 1500.0
    total_latency_warning_ms: float = 5000.0
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
    local_model_profile: str = "custom"
    local_model_gpu_profile: str = "none"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
