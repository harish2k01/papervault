# Product Scope

PaperVault is a long-lived, self-hosted personal document system. This page describes
what an operator and user can rely on today, the important limits to plan around, and
the intended product direction.

## Capabilities

| Area | Capability |
| --- | --- |
| Ingestion | PDF, scanned PDF, JPEG, and PNG uploads with size limits, hashing, object storage, immutable initial versions, queued processing, authenticated download, archive, and permanent delete |
| Extraction | Embedded PDF text, Tesseract OCR fallback, page-aware extracted text, normalized OCR word geometry/confidence, and database-safe text normalization |
| Document types | Extensible registry covering salary slips, employment letters/contracts, tax returns, Form 16, financial statements, insurance, medical reports, invoices, warranties, receipts, identity documents, property documents, and education certificates, with typed fields and locale-aware value normalization |
| Intelligence | Local, Ollama, and OpenAI-compatible analysis providers for summaries, keywords, entities, suggested tags, classification, confidence, and metadata extraction |
| Embeddings | Local deterministic, Ollama, and OpenAI-compatible embedding providers with dimension validation and provider/model provenance |
| Search | Keyword, semantic, and hybrid search; type/date/tag/issuer/organization filters; saved searches; deduplicated recent searches; PostgreSQL fallback |
| Questions | Natural-language questions over page chunks with tenant isolation, concept-coverage and document-type ranking, direct local answers for common amount/date/list intents, model-backed grounded answers, confidence, citations, and refusal when evidence is insufficient |
| Viewer | Responsive PDF/image viewer, page navigation, zoom, literal in-document search, page-aware results, text-layer highlighting, and OCR coordinate overlays |
| Lifecycle | Metadata editing, confidence review, source replacement, immutable versions, restore, download, extracted-text comparison, document and vault timelines, archive, permanent deletion, diagnostics, and retry |
| Organization | Manual and confidence-gated automatic tags, deterministic smart tags, reusable manual and dynamic collections, grid/list collection views, tag filtering, and explainable exact-file, exact-text, content-similarity, and OCR-similarity duplicate review with confirmation-gated archival |
| Notifications | Due date, expiry, renewal, and warranty reminders derived from document metadata with user-controlled status |
| Identity | Local login, JWT access tokens, OIDC authorization-code login, admin/user RBAC, runtime registration policy, user activation/role management, and guarded permanent deletion with owned-file cleanup |
| Administration | User and registration management plus non-secret runtime provider and provider-health visibility |
| Operations | Structured logs, Prometheus metrics, OpenTelemetry export, health probes, Docker Compose, GHCR workflows, Kubernetes, Helm, migration hooks, and Gateway API routing |

## Known Limits

- Classification and extraction quality depends on document layout, OCR quality,
  language, and selected model. The bundled evaluation fixtures are a contract check,
  not a comprehensive accuracy benchmark.
- Semantic retrieval loads a bounded set of owned chunks from PostgreSQL. Very large
  vaults need a dedicated chunk-vector projection.
- OCR geometry is available for newly processed Tesseract documents. Existing OCR
  documents must be reprocessed before coordinate highlights are available.
- Source versions are retained indefinitely. Automated retention policies and legal
  holds are not yet available.
- Reminders are generated during processing or manual refresh. Scheduled delivery,
  email, webhooks, and user timezone preferences are not available.
- Model provider settings are deployment configuration. Administrators can inspect
  health in the app, but secrets and model changes remain an operator responsibility.
- Similarity thresholds are conservative defaults, not universal truth. Operators with
  unusual OCR languages or highly repetitive forms should evaluate and tune them before
  resolving non-exact candidates.
- Explicit smart-tag refresh evaluates the owner's current library synchronously.
  Routine ingestion and edits update one document incrementally, but very large
  one-time rule changes may need a future background refresh job.

## Roadmap

1. A dedicated chunk index, embedding-version migration, index aliases, and search relevance evaluation.
2. Scheduled reminder generation, notification preferences, digests, email, and webhook delivery.
3. Configurable source-version retention and legal holds.
4. Password reset, optional email verification, refresh-token session management, MFA integration, and active-session revocation.
5. Backup, restore, disaster-recovery verification, export/import, and documented storage lifecycle procedures.
6. Malware scanning, configurable quotas, rate limiting, stronger content validation, and security event auditing.
7. Full browser end-to-end, accessibility, upgrade, rollback, backup, and restore suites in CI.
8. International OCR language packs, locale-aware classification, and per-locale evaluation corpora.
