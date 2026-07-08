# ADR 0007: Keep AI and Embeddings Behind Provider Interfaces

## Status

Accepted

## Context

PaperVault needs summaries, keywords, entities, suggested tags, classification, extracted metadata, and embeddings. Self-hosted users may want local-only processing, while other users may choose hosted AI providers. The rest of the application should not depend on a specific LLM or embedding API.

## Decision

Define provider interfaces for:

- document AI analysis
- embeddings

Phase 4 ships deterministic local providers:

- `LocalDocumentAIProvider`: rule-based summary, keyword/entity extraction, document classification, suggested tags, and metadata extraction.
- `HashingEmbeddingProvider`: deterministic local embeddings for development and self-hosted baseline behavior.

Provider outputs are persisted in:

- `document_ai_analyses`
- `document_embeddings`
- `document_metadata` for extracted document-type metadata

## Consequences

The system works without proprietary AI credentials. Hosted providers can be added as adapters later without changing upload, worker, or persistence workflows. The local providers are intentionally conservative and deterministic; they are a baseline, not a replacement for stronger model-backed extraction.
