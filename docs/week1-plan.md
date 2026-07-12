# Week 1 Target Plan

## Goal

Complete the foundation for database setup, document ingestion, OCR-aware extraction, and chunking strategies so Week 2 can focus on RAG retrieval pipelines and Redis caching.

## Deliverables

1. Infrastructure
   - PostgreSQL with pgvector extension
   - Redis
   - MinIO
   - Qdrant
   - Keycloak

2. Database
   - Tenants
   - Users
   - Roles
   - User-role mapping
   - Documents
   - Document chunks
   - Processing jobs
   - Audit logs

3. Chunking Strategy
   - Section-aware splitting
   - 500-900 token target range
   - 80-150 token overlap
   - Parent metadata carried into each chunk
   - RBAC metadata attached to each chunk
   - OCR-used flag attached to each chunk

4. OCR and Extraction
   - Native extraction first
   - OCR fallback for scanned/low-text documents
   - Tesseract-compatible abstraction
   - Parser warnings surfaced to ingestion result

5. Tests
   - Chunk count
   - Overlap behavior
   - Metadata propagation
   - Plain text extraction

## Week 1 Exit Criteria

- `docker compose up -d postgres redis minio qdrant keycloak` starts core services.
- Schema initializes in PostgreSQL.
- `pytest` passes.
- Ingestion endpoint can parse a local text/PDF/DOCX file when parser dependencies are installed.
- Every generated chunk includes tenant, document, visibility, roles, file name, MIME type, and OCR metadata.

## Known Decisions For Week 2

- Use Qdrant for primary vector search if 1 TB scale is prioritized.
- Keep pgvector available for metadata-coupled retrieval and smaller deployments.
- Add Celery workers for extraction, OCR, chunking, and embedding jobs.
- Add Redis query cache and semantic cache.
- Add reranker model after retrieval baseline is measured.
