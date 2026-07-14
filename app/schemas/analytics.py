from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
    cancelled: int = 0
    dead_lettered: int = 0
    recent_failures: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)


class QueryAnalytics(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    average_retrieval_ms: float = 0.0
    average_total_ms: float = 0.0
    p95_retrieval_ms: float = 0.0
    p95_total_ms: float = 0.0
    recent_average_total_ms: float = 0.0
    model_latency_buckets: list[ModelLatencyBucket] = Field(default_factory=list)


class ModelLatencyBucket(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_key: str
    total: int = 0
    average_total_ms: float = 0.0
    p95_total_ms: float = 0.0


class RetrievalAnalytics(BaseModel):
    vector_index_backend: str = "memory"
    reranker_runtime: str = "none"
    average_retrieval_ms: float = 0.0
    p95_retrieval_ms: float = 0.0
    retrieval_warning_ms: float = 1500.0
    retrieval_attention: bool = False
    qdrant: QdrantAnalytics | None = None


class QdrantAnalytics(BaseModel):
    ready: bool = False
    collection_name: str = ""
    points_count: int = 0
    indexed_vectors_count: int = 0
    segments_count: int = 0
    status: str = "unknown"
    optimizer_status: str = "unknown"
    message: str = ""


class EvaluationAnalytics(BaseModel):
    cases: int = 0
    passed: int = 0
    failed: int = 0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_relevance: float = 0.0
    answer_groundedness: float = 0.0
    last_run_at: str | None = None
    trend: list[EvaluationTrendPoint] = Field(default_factory=list)


class EvaluationTrendPoint(BaseModel):
    created_at: str
    cases: int = 0
    failed: int = 0
    context_precision: float = 0.0
    answer_groundedness: float = 0.0


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
    retrieval: RetrievalAnalytics
    evaluation: EvaluationAnalytics
    recent_events: list[AuditEvent] = Field(default_factory=list)
