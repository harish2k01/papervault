# Database

PostgreSQL stores metadata and relationships. Original PDFs and images remain in S3-compatible object storage.

## Tables

- `users`: local and OIDC identities, roles, active state, password hashes, and last login.
- `instance_settings`: singleton runtime policy overridden by administrators.
- `documents`: owner, object reference, hash, lifecycle and review state, processing diagnostics, type, issuer, date, organization, and summary.
- `document_versions`: immutable object-storage references, original filename/media type, current-source marker, and revision provenance.
- `document_duplicate_fingerprints`: one algorithm-versioned fingerprint for each document's current successful extraction, including normalized-text hash, MinHash signature, source, and bounded size metrics.
- `document_duplicate_buckets`: indexed locality-sensitive hash bands used to generate similarity candidates without an all-pairs scan.
- `document_metadata`: versioned structured extraction payloads.
- `document_text_extractions`: current and historical extraction outcomes.
- `document_text_pages`: ordered page text for viewer search and page navigation.
- `document_text_blocks`: normalized OCR word geometry and confidence for precise viewer highlights.
- `document_text_chunks`: page-bound retrieval chunks, embedding provider metadata, vectors, and source hashes.
- `document_ai_analyses`: summaries, keywords, entities, suggested tags, category, confidence, and extracted metadata.
- `document_embeddings`: provider/model metadata, vectors, and source hashes.
- `tags` and `document_tags`: user-owned tags and assignments.
- `timeline_events`: append-only user/document activity.
- `saved_searches` and `recent_searches`: reusable queries and search history.
- `notifications`: due-date and expiry reminders.

## Document Types

Document types are application registry keys rather than database enums. Adding a type does not require a database migration. The registry and typed metadata fields live in `apps/api/src/papervault_api/documents/domain/document_types.py`.

## Versioned Data

Metadata, text extraction, AI analysis, and document embeddings retain historical rows and mark one row current for each document. Text extractions reference the source version that produced them. Retrieval chunks belong to a specific extraction, so the current extraction determines which chunks can support answers. Duplicate fingerprints reference that same current extraction and are removed when a source version changes. This permits reprocessing, source comparison, restoration, and similarity validation without reusing stale derived data.

## Search Projection

OpenSearch is a derived projection. PostgreSQL and object storage contain enough information to rebuild it. Search mapping versions should use versioned index names and controlled rebuilds.

## Migrations

Alembic migrations are mandatory before API and worker rollout. The Helm chart runs them as a pre-upgrade hook. Migration and constraint names must fit PostgreSQL's 63-character identifier limit, and migration validation should include the PostgreSQL dialect rather than SQLite alone.
