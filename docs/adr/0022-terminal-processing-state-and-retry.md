# ADR 0022: Terminal Processing State And Retry

## Status

Accepted

## Context

Provider output can contain text that is valid in Python but invalid for PostgreSQL, and unexpected task failures can occur after an upload transaction has committed. Rolling back the worker session alone leaves the document in a queued or processing state with no user recovery path.

## Decision

Normalize extracted text at the processing persistence boundary and remove database-unsafe control characters. Commit `processing` before expensive work begins. Record a user-safe terminal failure and completion timestamp when extraction fails or the worker raises unexpectedly.

Allow owners to re-enqueue failed and stale queued documents without uploading the source again. Reject reprocessing while an active job is running and keep archive terminal.

## Consequences

- Provider-specific text defects cannot poison the extraction transaction.
- Users can distinguish queued, active, failed, and completed processing.
- Detailed exceptions remain in structured worker logs while the API exposes a safe diagnostic.
- Retry is at-least-once; a future processing-attempt table can add attempt history and stronger deduplication.
