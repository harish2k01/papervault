# ADR 0012: Publish Images to GHCR and Deploy with Helm

## Status

Accepted

## Context

PaperVault needs a repeatable self-hosted deployment path. Docker Compose is useful for development, but long-running self-hosted deployments commonly need Kubernetes manifests, image provenance, migration execution, and configurable runtime secrets.

## Decision

Phase 9 adds:

- GitHub Actions workflow for API, worker, and web image publishing to GHCR
- Helm chart resources for API, worker, web, services, config, secrets, and migration jobs
- optional Gateway API `HTTPRoute` routing for clusters with a managed Gateway controller
- optional lab-only PostgreSQL, Redis, and MinIO resources for smoke testing
- chart validation in CI
- external dependency assumptions for PostgreSQL, Redis, object storage, and OpenSearch
- non-root image/runtime hardening for API, worker, and web containers

The Helm chart remains production-oriented around external stateful services. Bundled
stateful resources are restricted to an explicit lab profile and are not the production
default.

## Consequences

Self-hosters can build and publish images through GitHub and deploy the application
workloads with Helm. The trade-off is that production operators must still provide and
back up PostgreSQL, Redis, object storage, and OpenSearch separately. The lab profile
improves smoke-test ergonomics, but it must not be treated as a backup-ready production
database or object-storage stack.
