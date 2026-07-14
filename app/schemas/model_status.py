from pydantic import BaseModel, ConfigDict


class ModelRuntimeStatus(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    runtime: str
    model_name: str
    ready: bool
    message: str
    base_url: str | None = None


class ModelPerformanceStatus(BaseModel):
    retrieval_warning_ms: float
    total_warning_ms: float


class ModelStatusResponse(BaseModel):
    llm_provider: str
    embedding_provider: str
    embedding: ModelRuntimeStatus
    answer: ModelRuntimeStatus
    vector_index: ModelRuntimeStatus
    reranker: ModelRuntimeStatus
    performance: ModelPerformanceStatus
