# ADR 0020: Duplicate Resolution By Archive

## Status

Accepted

## Context

PaperVault can detect exact duplicate files by SHA-256 hash. Users need a way to resolve those candidates, but deleting document rows or object-storage blobs is risky for a long-lived personal archive. Content and OCR similarity require separate confidence models; this decision covers exact-hash confidence only.

## Decision

Add an owner-scoped duplicate merge use case for exact-hash groups. The user chooses one document to keep and selected redundant copies to archive. The backend validates that every document belongs to the user, is active, and has the same SHA-256 hash before archiving anything.

Archived duplicate documents keep their metadata, timeline, versions, and object-storage references. Merge writes timeline events and refreshes the search projection on a best-effort basis.

Document processing treats archive as terminal. A queued worker exits without processing an already archived document and never replaces an archived status with a processing outcome.

## Consequences

- Duplicate cleanup is reversible at the data level because rows and blobs are retained.
- The default document list, search, and duplicate candidate query stop showing archived copies.
- The merge workflow does not consolidate metadata, tags, or versions into the kept document yet.
- Fuzzy duplicate detection and physical object cleanup remain future work.
