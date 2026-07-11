# Product Scope

This document maps PaperVault to its intended product capabilities. It separates behavior available in the repository from work that still needs a production implementation.

## Available

| Area | Capability |
| --- | --- |
| Ingestion | PDF, scanned PDF, JPEG, and PNG uploads with size limits, hashing, object storage, immutable initial versions, and queued processing |
| Extraction | Embedded PDF text, Tesseract OCR fallback, page-aware extracted text, and database-safe text normalization |
| Document types | Registry covering salary slips, employment letters/contracts, tax returns, Form 16, statements, insurance, medical reports, invoices, warranties, receipts, identity documents, property documents, and education certificates |
| Intelligence | Local deterministic summaries, keywords, entities, suggested tags, classification, confidence, metadata extraction, and embeddings behind provider interfaces |
| Search | Keyword, semantic, and hybrid search; type/date/tag/issuer/organization filters; saved searches; recent searches; PostgreSQL fallback |
| Questions | Natural-language questions over page chunks with tenant isolation, extractive grounded answers, confidence, document/page citations, and refusal when evidence is insufficient |
| Viewer | Responsive PDF viewer, page navigation, zoom, literal in-document search, page-aware results, and text-layer highlighting |
| Lifecycle | Metadata editing, archive, version history display, document timeline, processing diagnostics, and retry for failed or stale queued jobs |
| Organization | Manual tags, accepted AI tag suggestions, tag filtering, and exact-hash duplicate resolution by archive |
| Notifications | Due date, expiry, renewal, and warranty reminders derived from document metadata with user-controlled status |
| Identity | Local login, JWT access tokens, OIDC authorization-code login, admin/user RBAC, runtime registration policy, and user activation/role management |
| Operations | Structured logs, Prometheus metrics, OpenTelemetry export, health probes, Docker Compose, GHCR workflows, Kubernetes, Helm, migration hooks, and Gateway API routing |
| Testing | Backend unit/integration/API tests, frontend component tests, migration checks, Helm smoke tests, and public-route smoke tooling |

## Partial

| Area | What exists | What remains |
| --- | --- | --- |
| Automatic classification | Rule-based classifier and complete type registry | Broader training/evaluation corpus, provider-backed classification, and per-type accuracy reporting |
| Structured extraction | Typed schemas for key document families and rule-based extraction | Robust extractors for every registered type, locale-aware dates/currency, tables, and human review queues |
| AI providers | Stable analysis and embedding interfaces with local implementations | Configurable model-backed providers such as Ollama/OpenAI-compatible APIs and provider health/configuration UI |
| Semantic search | Stored document/chunk embeddings, OpenSearch document vector queries, and chunk-level grounded retrieval | Production embedding model selection, dedicated chunk index, evaluation, and migration between embedding versions |
| Notifications | Reminder records and refresh after processing/metadata changes | Scheduled reconciliation, delivery channels, digests, and timezone-aware notification preferences |
| Versions | Immutable initial version records and version history display | Replace/upload-new-version workflow, comparison, restore, and retention policy |
| Accessibility | Semantic controls, keyboard focus styles, responsive layouts | Automated accessibility checks and full screen-reader/browser matrix validation |
| End-to-end testing | API/cluster smoke tests and browser-assisted verification | Committed Playwright workflows covering authentication, upload, OCR, search, retry, settings, and restore paths |

## Planned

The following original requirements are not yet implemented and must remain in the roadmap:

1. Content-similarity and OCR-similarity duplicate detection in addition to exact hashes.
2. Smart tags, reusable collections, and optional folder-style views.
3. A vault-wide timeline workspace rather than document-only history.
4. Pixel-accurate OCR highlights using persisted word/line bounding boxes.
5. Complete provider ecosystem for model-backed summaries, extraction, grounded answers, embeddings, and optional remote OCR.
6. Scheduled reminder generation and email/webhook notification delivery.
7. Document replacement, version comparison, restore, permanent deletion, and configurable retention.
8. Password reset, optional email verification, refresh-token/session management, MFA integration, and active-session revocation.
9. Backup, restore, disaster-recovery verification, export/import, and documented storage lifecycle procedures.
10. Malware scanning, configurable quotas, rate limiting, stronger content validation, and security event auditing.
11. Index aliases, zero-downtime OpenSearch schema/embedding migrations, and search relevance evaluation.
12. Full browser E2E, accessibility, upgrade, rollback, backup, and restore test suites in CI.
13. International OCR language packs plus locale-aware document classification, currency, and date parsing.

## Recommended Delivery Order

1. Provider-backed AI, answer, and embedding configuration with evaluation fixtures.
2. Complete extraction coverage and OCR geometry.
3. Version replacement, global timeline, smart organization, and similarity duplicates.
4. Scheduled notifications and user delivery preferences.
5. Backup/restore, security hardening, session management, and production E2E coverage.
