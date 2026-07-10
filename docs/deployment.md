# Deployment Guide

The Helm chart deploys PaperVault application workloads and expects production stateful dependencies to be provided separately.

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
- Keep `PAPERVAULT_SEARCH_QUERY_FALLBACK_ENABLED=true` unless you intentionally want OpenSearch outages to fail user-facing search.

## OIDC Login

PaperVault supports OIDC authorization-code login for providers such as Authentik
and Keycloak. Register this redirect URI with the provider:

```text
https://<papervault-host>/api/auth/oidc/callback
```

Set the corresponding runtime values:

```yaml
config:
  webAppUrl: https://papervault.example.com
  oidcIssuerUrl: https://idp.example.com/application/o/papervault/
  oidcClientId: papervault
  oidcRedirectUri: https://papervault.example.com/api/auth/oidc/callback
  oidcScopes: openid email profile
secret:
  values:
    oidcClientSecret: <client-secret>
```

OIDC login is enabled only when issuer URL, client id, client secret, and redirect
URI are all configured. The first OIDC user becomes `admin` if no users exist.
PaperVault does not automatically link an OIDC account to an existing local account
with the same email address.

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

## Gateway API

The chart can publish a Gateway API `HTTPRoute` when the cluster already provides a
Gateway controller such as Traefik:

```bash
helm upgrade --install papervault infra/helm/papervault \
  --namespace papervault \
  --set gateway.httpRoute.enabled=true \
  --set gateway.httpRoute.gatewayName=traefik-gateway \
  --set gateway.httpRoute.gatewayNamespace=traefik \
  --set gateway.httpRoute.sectionName=websecure \
  --set gateway.httpRoute.hostnames[0]=papervault.example.com
```

The route sends `/api/*` to the API service and rewrites the prefix before it
reaches FastAPI. All other paths go to the web service.

## Lab Dependencies

For single-node homelab testing, `labDependencies.enabled=true` deploys chart-managed
PostgreSQL, Redis, and MinIO resources. It can also deploy OpenSearch with
`labDependencies.opensearch.enabled=true`. This profile is intended for smoke tests
and developer clusters, not long-lived production data. Production deployments should
use operator-managed or external dependencies with explicit backup and restore
procedures.

The repository includes `infra/helm/papervault/values-lab.example.yaml` as a redacted
starting point for GHCR images, Gateway API routing, and chart-managed lab services.
Keep environment-specific values and secrets outside version control.

## Smoke Tests

The chart includes a Helm test pod that verifies the API service health endpoint from
inside the cluster:

```bash
helm test papervault --namespace papervault
```

The public route can be verified with the workflow smoke script:

```bash
python scripts/cluster_smoke.py \
  --base-url https://papervault.example.com/api
```
