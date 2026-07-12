from pydantic import BaseModel, ConfigDict


class ModelRuntimeStatus(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    runtime: str
    model_name: str
    ready: bool
    message: str
    base_url: str | None = None


class ModelStatusResponse(BaseModel):
    llm_provider: str
    embedding_provider: str
    embedding: ModelRuntimeStatus
    answer: ModelRuntimeStatus
