# Deployment Guide

This guide covers the current production deployment boundary. The Helm chart deploys PaperVault application workloads and expects stateful dependencies to be provided separately.

## Required Services

- PostgreSQL
- Redis
- S3-compatible object storage
- OpenSearch or Elasticsearch-compatible search backend
- PaperVault API
- PaperVault worker
- PaperVault web frontend
- Tesseract and Poppler in worker images for local OCR

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
- Install required Tesseract language packs and set `PAPERVAULT_OCR_LANGUAGES` to match your document corpus.
- Tune `PAPERVAULT_OCR_MAX_PDF_PAGES`, `PAPERVAULT_OCR_TIMEOUT_SECONDS`, and worker concurrency based on CPU capacity.
- Keep `OPENSEARCH_DOCUMENTS_INDEX` versioned, for example `papervault-documents-v1`, so mapping changes can be rolled out through a new index and reindex operation.
- Monitor worker logs for `document_search_indexing_failed`; indexing is eventually consistent and does not fail document processing.

## Container Images

The `Images` GitHub Actions workflow publishes:

- `ghcr.io/<owner>/<repo>/api`
- `ghcr.io/<owner>/<repo>/worker`
- `ghcr.io/<owner>/<repo>/web`

Tags include branch names, Git tags, SHA tags, and `latest` on the default branch.

## Helm Deployment

Create or choose a namespace:

```bash
kubectl create namespace papervault
```

Deploy with chart-managed lab secrets:

```bash
helm upgrade --install papervault infra/helm/papervault \
  --namespace papervault \
  --set image.api.repository=ghcr.io/<owner>/<repo>/api \
  --set image.worker.repository=ghcr.io/<owner>/<repo>/worker \
  --set image.web.repository=ghcr.io/<owner>/<repo>/web \
  --set image.api.tag=<tag> \
  --set image.worker.tag=<tag> \
  --set image.web.tag=<tag>
```

For production, prefer an externally managed secret:

```bash
kubectl create secret generic papervault-runtime \
  --namespace papervault \
  --from-literal=DATABASE_URL='<database-url>' \
  --from-literal=REDIS_URL='<redis-url>' \
  --from-literal=S3_ACCESS_KEY_ID='<s3-access-key>' \
  --from-literal=S3_SECRET_ACCESS_KEY='<s3-secret-key>' \
  --from-literal=JWT_SIGNING_KEY='<jwt-signing-key>'

helm upgrade --install papervault infra/helm/papervault \
  --namespace papervault \
  --set secret.create=false \
  --set secret.existingSecret=papervault-runtime
```
