# ADR 0017: Document Tag Management

## Status

Accepted

## Context

Tags are central to PaperVault's organization model, but the web app could only
use tags as search filters. The backend already had owner-scoped tag creation,
assignment, timeline events, and document detail responses, while OpenSearch
queries can filter by tag slug. The missing workflow was accepting suggested
tags and managing manual tags from the document review surface.

## Decision

Add tag management to document detail:

- Assigned tags are shown with detach actions.
- Existing tags can be attached from an owner-scoped selector.
- New manual tags can be created and immediately attached to the current document.
- AI-suggested tags are accepted explicitly; accepting a suggestion reuses an
  existing tag with the same slug or creates a manual tag before attachment.
- Tag attach and detach API routes refresh the affected OpenSearch projection on
  a best-effort basis after the database transaction commits.

## Consequences

Suggested tags remain recommendations until a user accepts them, which avoids
silently changing the user's organization model. PostgreSQL remains the source
of truth for tag assignments and timeline history. OpenSearch is refreshed after
tag changes for normal operation, but temporary indexing failures do not reject
the user's tag mutation; the projection can still be repaired with the existing
owner-scoped reindex endpoints.
