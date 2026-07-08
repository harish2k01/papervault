# ADR 0005: Separate Upload Persistence from Document Processing

## Status

Accepted

## Context

Uploading a document should not require OCR, text extraction, AI extraction, or search indexing to complete during the HTTP request. Those operations are slower, more failure-prone, and may depend on external providers or system packages.

## Decision

The upload API performs only request-bound work:

- Validate supported file type.
- Stage the stream to a temporary file.
- Compute SHA-256 and file size.
- Store the file in S3-compatible object storage.
- Persist `documents`, `document_versions`, and a `timeline_events` row.
- Enqueue asynchronous document processing.

Celery workers own post-upload processing. Phase 3 workers download the stored file and create a `document_text_extractions` record.

## Consequences

Uploads can succeed even if processing later fails. The document status tracks that lifecycle. Exact duplicate detection can use the stored SHA-256 in a later phase without rereading object storage.
