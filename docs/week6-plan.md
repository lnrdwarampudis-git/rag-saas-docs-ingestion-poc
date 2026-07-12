# Week 6 Suggested Target Plan

## Goal

Move ingestion from a synchronous demo path toward a production-style background processing model. This is the next best improvement because large PDFs, Office files, OCR, and 1 TB-scale data sets should not block API requests or browser sessions while parsing/chunking runs.

## Why This Next

- It makes uploads feel reliable for large documents.
- It turns the existing `processing_jobs` table into a real operational feature.
- It gives the UI a clear status lifecycle: queued, processing, completed, failed, retrying.
- It creates the foundation for later scale work such as worker autoscaling, OCR queues, vector-index rebuilds, and resumable uploads.

## Delivered Scope

1. Job creation API
   - `POST /api/v1/documents/upload-async` accepts multipart files without breaking the existing synchronous upload route.
   - The backend stores the saved file reference, creates a pending document, creates a processing job, and returns `202 Accepted` with `document_id` and `job_id`.

2. Worker process
   - `python -m app.worker` polls Redis and runs queued jobs.
   - The same parser/chunker/persistence path is reused by synchronous ingestion and worker processing.
   - Job status, stage, attempts, and errors are stored in PostgreSQL when persistence is enabled.

3. Document status API
   - `GET /api/v1/processing-jobs/{job_id}` returns job state.
   - `POST /api/v1/processing-jobs/{job_id}/run` runs one job directly for local smoke testing.
   - Responses are tenant scoped.

4. UI progress
   - The Upload panel now includes "Upload to queue."
   - The UI shows queued/processing/completed/failed job cards and polls until terminal status.

5. Tests
   - API E2E tests cover queued upload, job status lookup, explicit processing, retrieval after completion, and tenant-scoped job visibility.

## Exit Criteria

- Upload returns quickly with a job id.
- Worker processes the file and persists chunks without blocking the API request.
- Document Management shows queued/processing/completed/failed states.
- Failed jobs record useful error messages.
- Backend tests and frontend build pass.

## Follow-Ups

- Direct-to-MinIO multipart upload for very large files.
- Separate OCR-heavy jobs into a dedicated queue.
- Add worker concurrency controls and rate limits per tenant.
- Add operational metrics: queue depth, processing duration, failure rate, and documents processed per hour.
- Add authorized retry controls for failed jobs.
