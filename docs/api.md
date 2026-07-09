# API Documentation

FastAPI exposes OpenAPI documentation at `/docs` and `/openapi.json` when enabled.

The API includes health endpoints:

- `GET /health/live`: process liveness
- `GET /health/ready`: dependency readiness placeholder
- `GET /health`: aggregate health response

## Documents

Document endpoints:

- `POST /documents/uploads`: multipart PDF/image upload.

Supported content types:

- `application/pdf`
- `image/jpeg`
- `image/png`

Development authentication fallback:

- `X-PaperVault-User-Id`: required UUID
- `X-PaperVault-User-Email`: optional email

These headers are accepted only when `PAPERVAULT_AUTH_ALLOW_DEV_HEADERS=true` and `PAPERVAULT_ENV` is not `production`. Production callers should use bearer tokens from `/auth/login`.

Successful uploads persist the original file in object storage, create document metadata rows, create a version row, append a timeline event, and enqueue worker processing.

Additional document endpoints:

- `GET /documents`: list documents
- `GET /documents/{document_id}`: document detail with AI summary, metadata, tags, timeline, and extraction status
- `GET /documents/{document_id}/file`: authenticated document file response for the built-in viewer
- `GET /documents/{document_id}/timeline`: document timeline events
- `GET /documents/duplicates/candidates`: exact-hash duplicate candidate groups

## Search

- `POST /search`: keyword, semantic, or hybrid search with filters
- `POST /search/saved`: save a search
- `GET /search/saved`: list saved searches
- `GET /search/recent`: list recent searches
- `POST /search/index/documents/{document_id}`: reindex one owned document
- `POST /search/index/rebuild?limit=500`: rebuild the current user's document index projection

Phase 10 search uses OpenSearch for user-facing keyword, semantic, and hybrid queries when `PAPERVAULT_SEARCH_QUERY_BACKEND=opensearch` and indexing is enabled. PostgreSQL remains the source of truth and fallback query path when OpenSearch errors or is disabled.

## Tags

- `GET /tags`: list tags
- `POST /tags`: create a manual tag
- `POST /documents/{document_id}/tags/{tag_id}`: attach a tag
- `DELETE /documents/{document_id}/tags/{tag_id}`: detach a tag

## Notifications

- `GET /notifications`: list notifications
- `POST /notifications/sync/{document_id}`: regenerate document notifications from current metadata
- `PATCH /notifications/{notification_id}`: mark a notification `pending`, `read`, or `dismissed`

## Authentication and Users

- `GET /auth/config`: public auth capability discovery
- `POST /auth/register`: create a local account and return a bearer token
- `POST /auth/login`: authenticate a local account and return a bearer token
- `GET /auth/oidc/start`: redirect the browser to the configured OIDC provider
- `GET /auth/oidc/callback`: exchange an authorization code, create or update the OIDC user, and redirect back to the web app with a PaperVault bearer token in the URL fragment
- `GET /auth/me`: current user profile
- `GET /users`: admin-only user listing
- `PATCH /users/{user_id}`: admin-only role, display name, or active-state update

The first registered local user is assigned the `admin` role. Later users are assigned `user` by default.
The first OIDC-created user is also assigned `admin` when no users exist. OIDC login is advertised
only when issuer URL, client id, client secret, and redirect URI are configured.
