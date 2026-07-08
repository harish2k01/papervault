# ADR 0001: Start as a Modular Monolith

## Status

Accepted

## Context

PaperVault has multiple complex capabilities: upload, OCR, classification, metadata extraction, search, timeline, duplicate detection, notifications, and authentication. Splitting these into separate services too early would add deployment and consistency complexity before the domain boundaries are proven.

## Decision

Start with a modular monolith:

- One FastAPI API process.
- One Celery worker process using the same backend package.
- Feature-first packages with explicit application services and provider interfaces.
- Separate infrastructure services for PostgreSQL, Redis, MinIO/S3, and OpenSearch.

## Consequences

This keeps local development and self-hosting practical while preserving the option to split heavy workloads later. The cost is that code boundaries must be enforced through project structure, review, and tests rather than service boundaries.
