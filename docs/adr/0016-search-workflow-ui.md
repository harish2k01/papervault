# ADR 0016: Search Workflow UI

## Status

Accepted

## Context

The backend already supports keyword, semantic, and hybrid search, advanced filters,
saved searches, and recent searches. The web app still exposed only a keyword-style
search box, so users could not realistically search by document type, issuer, tag,
date range, or replay saved searches.

## Decision

Add a search workflow panel to the document list screen:

- Search mode, document type, tag, issuer, organization, date range, and archived
  inclusion are explicit form controls.
- Saved and recent searches are compact shortcut lists that rehydrate the same
  typed search request used by manual search.
- The frontend discovers document types from `/documents/types` instead of
  hardcoding the registry.
- Tags are loaded from the existing tag API and used by slug for search filters.

## Consequences

The frontend now exercises the same filter contract as the API and OpenSearch query
adapter. Document type additions remain centralized in the backend registry. Saved
searches are replayed as plain search requests rather than creating a separate
execution path.
