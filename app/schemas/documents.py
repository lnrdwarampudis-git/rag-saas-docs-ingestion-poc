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
    extraction_ms: float = 0.0
    ocr_ms: float = 0.0
    ocr_pages: int = 0


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
    extraction_warnings: list[str] = Field(default_factory=list)
    extraction_ms: float = 0.0
    ocr_ms: float = 0.0
    ocr_pages: int = 0
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
    retry_history: list[str] = Field(default_factory=list)


class UploadSessionCreateRequest(BaseModel):
    file_name: str
    byte_size: int = Field(gt=0)
    visibility: str = Field(default="tenant", pattern="^(private|tenant|role)$")
    allowed_role_names: list[str] = Field(default_factory=list)
    force_ocr: bool = False


class UploadSessionStatus(BaseModel):
    upload_session_id: UUID
    file_name: str
    byte_size: int
    part_size_bytes: int
    uploaded_parts: list[int] = Field(default_factory=list)
    complete: bool = False
    storage_backend: str = "filesystem"


class UploadPartPresignResponse(BaseModel):
    upload_session_id: UUID
    part_number: int
    method: str = "PUT"
    url: str
    expires_in_seconds: int
