# ADR 0029: Deterministic Smart Tags And Collections

## Status

Accepted

## Context

Users need reusable organization that scales beyond manually attaching every tag.
Folder semantics would imply moving a document into one place, while PaperVault needs
the same document to participate in multiple workflows. AI-only organization would
also make membership difficult to predict, audit, and reproduce after a model change.

## Decision

PaperVault treats collections as user-owned views over documents rather than storage
locations. Manual collections materialize explicit document membership. Dynamic
collections persist a typed document rule and evaluate PostgreSQL source-of-truth
fields when read. The stored view preference supplies optional folder-style grid and
list presentation without changing object-storage keys.

Smart tags persist a deterministic rule and materialize normal document-tag links.
Rules can match document type, title, issuer, organization, and document date. Dynamic
collections may additionally match existing tags and include archived documents.
Smart tags cannot depend on tags, which avoids recursive rules and update cycles.

Conditions are combined with AND. Multiple values inside one condition are combined
with OR. Manual and AI tag assignments take precedence and are never removed by smart
rule reconciliation. Worker processing and document edits synchronize the affected
document; explicit full refresh reconciles existing libraries.

## Consequences

- A document can appear in several collections without duplicating or moving its source.
- Dynamic collection membership reflects current metadata and does not require a stale
  materialized projection.
- Smart tags work with existing filters and OpenSearch because they use the normal tag
  assignment model.
- Rule behavior is explainable and independent of model-provider drift.
- Explicit smart-tag refresh is linear in the owner's document count and may need a
  background job for very large libraries.
- Nested collections and arbitrary boolean rule trees are intentionally deferred until
  simpler rules demonstrate a real limitation.
