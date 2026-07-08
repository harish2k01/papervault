# Database Schema

Phase 2 establishes the core relational model. PostgreSQL stores metadata and relationships only; document binaries stay in object storage.

## Core Tables

- `users`: local and OIDC-backed users, password hashes for local accounts, roles, active state, and last login time.
- `documents`: one row per logical document, with owner, object-storage reference, hash, status, type key, optional issuer/date/organization, and summary.
- `document_versions`: immutable object-storage references for document revisions.
- `document_metadata`: versioned structured extraction payloads per document.
- `document_text_extractions`: embedded-text or OCR extraction results.
- `document_ai_analyses`: AI summaries, keywords, entities, suggested tags, classifications, and confidence.
- `document_embeddings`: vector payloads and source hashes for semantic search indexing.
- `tags`: user-owned manual, AI, or smart tags.
- `document_tags`: document/tag assignments with source and optional confidence.
- `timeline_events`: append-only user/document history events.
- `saved_searches`: user-owned reusable search definitions.
- `recent_searches`: user-owned search history.
- `notifications`: user-owned due-date and expiry notification records.

## Document Types

Document types are application-level keys such as `salary_slip`, `credit_card_statement`, and `insurance_policy`. They are not database enum values. This keeps adding new document types simple and avoids migrations for every classifier.

The registry lives in:

`apps/api/src/papervault_api/documents/domain/document_types.py`

## Metadata

Document-specific metadata is stored in `document_metadata.data` as JSON. Each record carries a schema name and version, which allows extractors to evolve without overwriting historical results.

Examples:

- Salary slip: employer, month, year, net salary, gross salary.
- Credit card statement: bank, statement period, due date, total due, minimum due.
- Insurance policy: provider, policy number, coverage, premium, expiry date.
- Invoice: vendor, invoice number, purchase date, warranty, total amount.

## Deferred Tables

Search index projections, duplicate merge records, and auth refresh/session state are intentionally deferred to later phases.
