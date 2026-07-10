# ADR 0013: Use OpenSearch for User-Facing Search with PostgreSQL Fallback

## Status

Accepted

## Context

OpenSearch began as an eventually consistent projection while query execution remained in
PostgreSQL. That reduced rollout risk, but large document libraries need OpenSearch
scoring, text search, and vector search before PaperVault can scale beyond the
database-backed baseline.

## Decision

OpenSearch is the primary query path for `POST /search` when
`PAPERVAULT_SEARCH_QUERY_BACKEND=opensearch` and search indexing is enabled. The search
application service records recent searches, asks the OpenSearch query adapter first,
and falls back to the PostgreSQL scorer if OpenSearch fails and
`PAPERVAULT_SEARCH_QUERY_FALLBACK_ENABLED=true`.

The PostgreSQL implementation remains in the application layer as a source-of-truth
fallback. The OpenSearch adapter owns query DSL construction, filters, highlighting, and
hit parsing.

## Consequences

Users get the production search path without losing graceful behavior during search
cluster outages. The trade-off is that search results are eventually consistent with
document processing and can briefly differ from PostgreSQL after uploads, reprocessing,
or reindex operations. Operators that need strict failure visibility can disable fallback
and let OpenSearch errors surface to clients.
