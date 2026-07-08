# ADR 0002: Store Blobs Outside PostgreSQL

## Status

Accepted

## Context

PaperVault handles PDFs, scanned PDFs, images, OCR artifacts, and previews. Storing binary objects in PostgreSQL would make backups, migrations, and database performance harder to manage for self-hosted users.

## Decision

Store original and derived document files in S3-compatible object storage. PostgreSQL stores object keys, checksums, metadata, timeline events, permissions, and extraction state.

## Consequences

Self-hosted deployments need object storage such as MinIO. Application code must treat blob storage and database writes as separate operations and design workflows to recover from partial failures.
