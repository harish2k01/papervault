# Product Scope

PaperVault is a long-lived, self-hosted personal document system. This page describes
what an operator and user can rely on today, the important limits to plan around, and
the intended product direction.

## Capabilities

| Area | Capability |
| --- | --- |
| Ingestion | PDF, scanned PDF, JPEG, and PNG uploads with size limits, hashing, object storage, immutable initial versions, queued processing, authenticated download, archive, and permanent delete |
| Extraction | Embedded PDF text, Tesseract OCR fallback, page-aware extracted text, and database-safe text normalization |
| Document types | Registry covering salary slips, employment letters/contracts, tax returns, Form 16, statements, insurance, medical reports, invoices, warranties, receipts, identity documents, property documents, and education certificates |
| Intelligence | Local, Ollama, and OpenAI-compatible analysis providers for summaries, keywords, entities, suggested tags, classification, confidence, and metadata extraction |
| Embeddings | Local deterministic, Ollama, and OpenAI-compatible embedding providers with dimension validation and provider/model provenance |
| Search | Keyword, semantic, and hybrid search; type/date/tag/issuer/organization filters; saved searches; deduplicated recent searches; PostgreSQL fallback |
| Questions | Natural-language questions over page chunks with tenant isolation, local or model-backed grounded answers, confidence, document/page citations, and refusal when evidence is insufficient |
| Viewer | Responsive PDF viewer, page navigation, zoom, literal in-document search, page-aware results, and text-layer highlighting |
| Lifecycle | Metadata editing, archive, permanent deletion, version history display, document timeline, processing diagnostics, and retry for failed or stale queued jobs |
| Organization | Manual and confidence-gated automatic tags, tag filtering, and exact-hash duplicate resolution by archive |
| Notifications | Due date, expiry, renewal, and warranty reminders derived from document metadata with user-controlled status |
| Identity | Local login, JWT access tokens, OIDC authorization-code login, admin/user RBAC, runtime registration policy, and user activation/role management |
| Administration | User and registration management plus non-secret runtime provider and provider-health visibility |
| Operations | Structured logs, Prometheus metrics, OpenTelemetry export, health probes, Docker Compose, GHCR workflows, Kubernetes, Helm, migration hooks, and Gateway API routing |

## Known Limits

- Classification and extraction quality depends on document layout, OCR quality,
  language, and selected model. The bundled evaluation fixtures are a contract check,
  not a comprehensive accuracy benchmark.
- Semantic retrieval loads a bounded set of owned chunks from PostgreSQL. Very large
  vaults need a dedicated chunk-vector projection.
- OCR search highlights navigate to the correct page but do not draw pixel-accurate
  boxes because word geometry is not stored.
- Version history currently records the initial source; replace, compare, restore,
  and retention workflows are not available.
- Reminders are generated during processing or manual refresh. Scheduled delivery,
  email, webhooks, and user timezone preferences are not available.
- Model provider settings are deployment configuration. Administrators can inspect
  health in the app, but secrets and model changes remain an operator responsibility.

## Roadmap

1. Content-similarity and OCR-similarity duplicate detection in addition to exact hashes.
2. Smart tags, reusable collections, and optional folder-style views.
3. A vault-wide timeline workspace rather than document-only history.
4. Pixel-accurate OCR highlights using persisted word and line bounding boxes.
5. Broader per-document extraction schemas, locale-aware dates and currencies, table extraction, review queues, and quality reporting.
6. A dedicated chunk index, embedding-version migration, index aliases, and search relevance evaluation.
7. Scheduled reminder generation, notification preferences, digests, email, and webhook delivery.
8. Document replacement, version comparison, restore, and configurable retention.
9. Password reset, optional email verification, refresh-token session management, MFA integration, and active-session revocation.
10. Backup, restore, disaster-recovery verification, export/import, and documented storage lifecycle procedures.
11. Malware scanning, configurable quotas, rate limiting, stronger content validation, and security event auditing.
12. Full browser end-to-end, accessibility, upgrade, rollback, backup, and restore suites in CI.
13. International OCR language packs and locale-aware classification.
