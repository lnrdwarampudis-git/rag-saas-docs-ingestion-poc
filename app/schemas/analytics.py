from pydantic import BaseModel, Field


class DocumentAnalytics(BaseModel):
    total: int = 0
    embedded: int = 0
    pending: int = 0
    failed: int = 0
    chunks: int = 0
    ocr_documents: int = 0


class JobAnalytics(BaseModel):
    total: int = 0
    queued: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    recent_failures: list[str] = Field(default_factory=list)


class QueryAnalytics(BaseModel):
    total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    average_retrieval_ms: float = 0.0
    average_total_ms: float = 0.0


class EvaluationAnalytics(BaseModel):
    cases: int = 0
    passed: int = 0
    failed: int = 0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_relevance: float = 0.0


class AuditEvent(BaseModel):
    action: str
    resource_type: str
    resource_id: str | None = None
    actor: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str


class AnalyticsResponse(BaseModel):
    documents: DocumentAnalytics
    jobs: JobAnalytics
    queries: QueryAnalytics
    evaluation: EvaluationAnalytics
    recent_events: list[AuditEvent] = Field(default_factory=list)
