# Document reliability

PaperVault's primary workflow is to store an original document, extract its contents,
find it again, and inspect the source. A successful upload alone does not establish
that extraction, indexing, or later retrieval succeeded.

## Processing and search behavior

- Originals remain in object storage and are recorded as immutable source versions.
- Queued documents refresh automatically while the worker processes them.
- Embedded PDF text is preserved. Mixed PDFs also run OCR for pages without text.
- OCR page limits are explicit failures; later pages are not silently discarded.
- Optional analysis failure produces a review warning without hiding extracted text
  from keyword search. Model-backed summaries and embeddings remain unavailable
  until a successful retry.
- The workspace starts with keyword search. It does not require an embedding service.
- Hybrid search falls back to keyword search on embedding failure when fallback is
  enabled. Explicit semantic mode and disabled fallback continue to report failure.
- Database fallback scans the owner's complete eligible library in batches, with
  bounded result retention. Archived documents remain excluded unless requested.
- Search cards show matching excerpts as plain text. They are document covers, not
  rendered thumbnails of the source file.
- Keyword search retains numeric references, short names, and non-Latin text. Its
  tokens are independent of analysis keywords and existing embedding vectors.

## Regression coverage

| Scenario | Automated coverage |
| --- | --- |
| Original PDF upload, extraction, indexing, and later content retrieval while analysis is unavailable | Generated PDF, SQLite, in-memory object storage, and recording index |
| Exact content in a document older than the latest 500 uploads | Database search regression with 502 documents |
| Hybrid search while the embedding provider is unavailable | Provider failure regression; explicit semantic failure is also checked |
| A worker finishes before the upload request returns | Separate worker session, including lost queue acknowledgement |
| A PDF contains a digital cover and scanned attachment | Adapter composition test; scanned text and page ordering are checked |
| A scanned PDF exceeds its OCR page limit | Generated PDF and adapter preflight test |
| The UI follows a queued document to readiness | Component test verifying that preview fetching begins after polling |
| Search results explain a match | Component test for keyword requests and matching excerpts |
| Numeric references, short names, and non-Latin queries | Keyword scoring, excerpt, and database retrieval regressions |

Backend checks run from `apps/api`:

```sh
python -m pytest
python -m ruff check src tests
python -m mypy src
```

Frontend checks run from `apps/web`:

```sh
npm run lint
npm test -- --run
npm run build
```

## Verification limits

These tests do not establish production OCR accuracy or full deployment reliability.
The generated-PDF integration test uses real PDF extraction and application services,
with substitutes for object storage, model analysis, and the search index. Mixed-PDF
tests substitute OCR output; they do not benchmark Tesseract on photographed pages.

Production verification still requires PostgreSQL migrations, S3-compatible storage,
Redis/Celery task delivery and restart recovery, OpenSearch availability and indexing,
representative scanned documents, and backup restoration. Browser checks using
fixture API responses establish presentation and interaction behavior, not live
service connectivity. No production upgrade or data migration is implied by local
test results.

Search relevance, rotated or low-quality scans, multiple OCR languages, large-vault
performance, and model-backed answers require separate corpus-level evaluation.
The local hashing embedding provider is a lexical baseline, not a substitute for
semantic model evaluation.
