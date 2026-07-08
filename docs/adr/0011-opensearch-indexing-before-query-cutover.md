# ADR 0011: Add OpenSearch Indexing Before Query Cutover

## Status

Accepted

## Context

PaperVault needs full text, semantic, and hybrid search at production scale. Phase 5 delivered useful database-backed search while the document, AI, tag, notification, and auth contracts were still stabilizing. Replacing query execution and indexing in one step would make failures harder to isolate.

## Decision

Phase 8 introduces OpenSearch indexing before moving user-facing query execution:

- document search projections are built in an application service
- the worker indexes documents after extraction, AI processing, and notification generation
- the OpenSearch adapter owns index creation, upsert, and delete behavior
- the index stores metadata, tags, text, AI fields, and embedding vectors
- owner-scoped reindex endpoints allow operational rebuilds
- database-backed search remains the query path for this phase

## Consequences

OpenSearch can be validated and monitored independently of query cutover. The trade-off is temporary dual search state: PostgreSQL remains the source of truth, and OpenSearch is an eventually consistent projection. The next search hardening step can add OpenSearch-backed query execution, scoring tests, and fallback behavior.
