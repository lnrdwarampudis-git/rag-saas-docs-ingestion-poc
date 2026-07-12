# Week 6 Suggested Target Plan

## Goal

Move ingestion from a synchronous demo path toward a production-style background processing model. This is the next best improvement because large PDFs, Office files, OCR, and 1 TB-scale data sets should not block API requests or browser sessions while parsing/chunking runs.

## Why This Next

- It makes uploads feel reliable for large documents.
- It turns the existing `processing_jobs` table into a real operational feature.
- It gives the UI a clear status lifecycle: queued, processing, completed, failed, retrying.
- It creates the foundation for later scale work such as worker autoscaling, OCR queues, vector-index rebuilds, and resumable uploads.

## Proposed Scope

1. Job creation API
   - Keep upload accepting multipart files.
   - Store the file/object reference and create a `processing_jobs` row.
   - Return `202 Accepted` with `document_id` and `job_id` for asynchronous processing.

2. Worker process
   - Add a dedicated backend worker command for parsing, OCR, chunking, embedding, and persistence.
   - Use Redis as the local queue backend for the POC.
   - Update job status and error details in PostgreSQL.

3. Document status API
   - Add `GET /api/v1/processing-jobs/{job_id}`.
   - Include status, progress, timestamps, retry count, and latest error.
   - Keep all responses tenant/RBAC scoped.

4. UI progress
   - Show upload/job progress in Document Management.
   - Poll job status until completion or failure.
   - Add retry action for failed jobs if the caller has the right role.

5. Tests
   - Unit tests for job lifecycle transitions.
   - API E2E tests for queue, status, authorization, failure, and retry.
   - Frontend smoke coverage for queued-to-completed UI behavior.

## Exit Criteria

- Upload returns quickly with a job id.
- Worker processes the file and persists chunks without blocking the API request.
- Document Management shows queued/processing/completed/failed states.
- Failed jobs record useful error messages and can be retried by an authorized user.
- Backend tests and frontend build pass.

## Follow-Ups

- Direct-to-MinIO multipart upload for very large files.
- Separate OCR-heavy jobs into a dedicated queue.
- Add worker concurrency controls and rate limits per tenant.
- Add operational metrics: queue depth, processing duration, failure rate, and documents processed per hour.
