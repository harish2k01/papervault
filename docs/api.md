# API Documentation

FastAPI exposes OpenAPI documentation at `/docs` and `/openapi.json` when enabled.

The API includes health endpoints:

- `GET /health/live`: process liveness
- `GET /health/ready`: database-backed dependency readiness
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
- `GET /documents/types`: list supported document type keys, labels, and metadata field definitions
- `GET /documents/{document_id}`: document detail with AI summary, metadata, tags, timeline, and extraction status
- `PATCH /documents/{document_id}`: edit document title, type, date, issuer, or organization
- `PUT /documents/{document_id}/metadata`: replace current structured metadata with a manual metadata version
- `POST /documents/{document_id}/archive`: archive a document and hide it from default list/search results
- `POST /documents/{document_id}/reprocess`: retry a failed or stale queued document without uploading the source again
- `GET /documents/{document_id}/file`: authenticated document file response for the built-in viewer
- `GET /documents/{document_id}/text-search?query=salary&limit=50`: owner-scoped literal search over the current extracted text, returning bounded excerpts and page numbers when available
- `GET /documents/{document_id}/timeline`: document timeline events
- `GET /documents/duplicates/candidates`: exact-hash duplicate candidate groups
- `POST /documents/duplicates/merge`: keep one exact-hash duplicate and archive selected redundant copies

Document text search accepts a case-insensitive literal query between 2 and 200 characters and returns at most 100 matches. `total_matches` reports the complete count even when the response is limited. Legacy extractions without page rows remain searchable, but return `page_mapping_available=false` until they are reprocessed.

## Search

- `POST /search`: keyword, semantic, or hybrid search with filters
- `POST /search/saved`: save a search
- `GET /search/saved`: list saved searches
- `GET /search/recent`: list recent searches
- `POST /search/index/documents/{document_id}`: reindex one owned document
- `POST /search/index/rebuild?limit=500`: rebuild the current user's document index projection

Search uses OpenSearch for user-facing keyword, semantic, and hybrid queries when `PAPERVAULT_SEARCH_QUERY_BACKEND=opensearch` and indexing is enabled. PostgreSQL remains the source of truth and fallback query path when OpenSearch errors or is disabled.
Archived documents are excluded by default. Set `filters.include_archived=true` to include them.
Supported filters are document type, issuer, organization, tag slug, document date range, and archived inclusion.

## Questions

- `POST /questions/ask`: answer a natural-language question from the current user's ready documents

The request accepts a `question` between 3 and 1,000 characters. The response states whether the question was answered, includes a confidence score, and returns document/page citations with bounded evidence snippets. When the retrieval policy cannot find enough lexical support, PaperVault refuses to answer and returns no citations. Existing page text is chunked and embedded lazily on first use; newly processed documents materialize chunks during AI processing.

## Tags

- `GET /tags`: list tags
- `POST /tags`: create a manual tag
- `POST /documents/{document_id}/tags/{tag_id}`: attach a tag
- `DELETE /documents/{document_id}/tags/{tag_id}`: detach a tag

Tag assignment endpoints are owner-scoped, append `tags_changed` timeline events, and refresh the affected document's OpenSearch projection on a best-effort basis after PostgreSQL commits. Accepted AI-suggested tags use the same manual tag endpoints.

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
- `GET /admin/settings`: admin-only effective registration policy and non-secret runtime provider information
- `PATCH /admin/settings`: admin-only update of the persisted local-registration policy

The first registered local user is assigned the `admin` role. Later users are assigned `user` by default.
The first OIDC-created user is also assigned `admin` when no users exist. OIDC login is advertised
only when issuer URL, client id, client secret, and redirect URI are configured.
