# Deployment Guide

This guide is a placeholder for production deployment details. Phase 1 includes deployable building blocks but does not yet define a hardened production profile.

## Required Services

- PostgreSQL
- Redis
- S3-compatible object storage
- OpenSearch or Elasticsearch-compatible search backend
- PaperVault API
- PaperVault worker
- PaperVault web frontend

## Production Notes

- Replace every development secret.
- Set a long random `JWT_SIGNING_KEY`.
- Set `PAPERVAULT_AUTH_ALLOW_DEV_HEADERS=false`.
- Set `PAPERVAULT_LOCAL_REGISTRATION_ENABLED=false` after creating the initial administrator.
- Use TLS at the ingress layer.
- Use managed backups for PostgreSQL and object storage.
- Pin container image tags.
- Enable OpenTelemetry export to your tracing backend.
- Configure OIDC before relying on external identity providers.
