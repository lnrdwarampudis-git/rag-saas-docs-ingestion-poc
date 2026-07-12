from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    tenant_id: UUID
    query: str = Field(min_length=1)
    role_names: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    cached: bool
    citations: list[dict]
    metrics: dict[str, float | int]
