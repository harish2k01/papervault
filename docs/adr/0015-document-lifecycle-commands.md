# ADR 0015: Document Lifecycle Commands

## Status

Accepted

## Context

PaperVault already stores timeline events, metadata versions, document versions, and
an archived document status. Earlier phases exposed read-only detail views but did
not provide command paths for long-lived document maintenance.

## Decision

Add a document lifecycle application service for:

- editing document fields
- replacing structured metadata with a manual current metadata record
- archiving documents
- writing timeline events for lifecycle changes

Default document lists, duplicate detection, and search exclude archived documents.
The search API keeps an explicit `include_archived` filter for callers that need
archived results.

Lifecycle routes update PostgreSQL first and then refresh the OpenSearch projection
best-effort. Search indexing errors are logged and do not fail the user-facing
metadata edit or archive action.

## Consequences

The database remains the source of truth for lifecycle state. OpenSearch may lag
briefly or require a reindex after an outage, but users can still edit and archive
documents while the search backend is degraded. Manual metadata replacement creates
new metadata records instead of mutating previous extraction output, preserving an
audit trail for future history views.
