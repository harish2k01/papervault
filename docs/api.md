# API Documentation

FastAPI exposes OpenAPI documentation at `/docs` and `/openapi.json` when enabled.

The API includes health endpoints:

- `GET /health/live`: process liveness
- `GET /health/ready`: dependency readiness placeholder
- `GET /health`: aggregate health response

## Documents

Phase 3 adds the first document endpoint:

- `POST /documents/uploads`: multipart PDF/image upload.

Supported content types:

- `application/pdf`
- `image/jpeg`
- `image/png`

Current authentication boundary:

- `X-PaperVault-User-Id`: required UUID
- `X-PaperVault-User-Email`: optional email

This header boundary is temporary. OIDC/local-login integration will replace it in the authentication phase.

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

Phase 5 search is database-backed. OpenSearch indexing is deferred until the search contracts settle.

## Tags

- `GET /tags`: list tags
- `POST /tags`: create a manual tag
- `POST /documents/{document_id}/tags/{tag_id}`: attach a tag
- `DELETE /documents/{document_id}/tags/{tag_id}`: detach a tag

## Notifications

- `GET /notifications`: list notifications
- `POST /notifications/sync/{document_id}`: regenerate document notifications from current metadata
- `PATCH /notifications/{notification_id}`: mark a notification `pending`, `read`, or `dismissed`
