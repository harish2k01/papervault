# ADR 0004: Store Extracted Metadata as Versioned Records

## Status

Accepted

## Context

PaperVault must support many document types, and each type has different metadata. A salary slip has salary fields, a credit card statement has due dates and amounts, and an insurance policy has policy and expiry fields. New document types should be easy to add without repeated schema migrations.

## Decision

Keep `documents.document_type` as a string key and store extracted metadata in `document_metadata` records:

- `schema_name`: document type or extraction schema key.
- `schema_version`: version of that extraction schema.
- `data`: JSON object containing extracted fields.
- `source`: `ai`, `ocr`, `manual`, or `import`.
- `confidence_score`: optional confidence from the extractor.
- `is_current`: marks the active metadata record for a document.

Known document types and their expected metadata fields are defined in the application registry, not as a database enum.

## Consequences

Adding a document type generally requires adding a registry definition and extraction logic, not a database migration. The trade-off is that field-level validation lives in application code and tests rather than rigid relational columns.
