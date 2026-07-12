from uuid import UUID

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
