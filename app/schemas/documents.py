from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    local_path: str
    visibility: str = Field(default="tenant", pattern="^(private|tenant|role)$")
    allowed_role_names: list[str] = Field(default_factory=list)
    force_ocr: bool = False


class ChunkDTO(BaseModel):
    chunk_index: int
    text: str
    token_count: int
    metadata: dict


class DocumentIngestResult(BaseModel):
    document_id: UUID
    file_name: str
    chunks_created: int
    ocr_used: bool
    extraction_warnings: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    document_id: UUID
    tenant_id: UUID
    file_name: str
    status: str
    visibility: str
    allowed_role_names: list[str] = Field(default_factory=list)
    chunks_created: int
    ocr_used: bool
    byte_size: int | None = None
    mime_type: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    latest_audit_action: str | None = None


class DocumentDetail(DocumentSummary):
    chunks: list[ChunkDTO] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary] = Field(default_factory=list)


class ProcessingJobStatus(BaseModel):
    job_id: UUID
    document_id: UUID
    file_name: str
    status: str
    stage: str
    attempts: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
