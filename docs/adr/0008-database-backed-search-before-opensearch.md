# ADR 0008: Start Search with Database-Backed Hybrid Scoring

## Status

Accepted

## Context

PaperVault needs keyword, semantic, and hybrid search. OpenSearch is part of the target architecture, but introducing indexing, mapping migrations, reindexing, and failure recovery before the API contracts settle would add operational complexity.

## Decision

Phase 5 implements search through PostgreSQL-backed records:

- keyword scoring over document title, filename, issuer, organization, summary, and extracted text
- semantic scoring over stored document embeddings
- hybrid scoring that combines keyword and semantic scores
- filters for document type, issuer, organization, tags, and dates
- saved and recent searches

OpenSearch indexing remains the production search target for a later hardening step.

## Consequences

The application has useful search behavior without requiring a search cluster to be healthy. The trade-off is that this is not intended for large libraries; OpenSearch indexing is still needed before PaperVault scales to heavy personal archives.
