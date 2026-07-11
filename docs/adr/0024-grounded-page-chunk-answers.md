# ADR 0024: Grounded Page-Chunk Answers

## Status

Accepted

## Context

Natural-language answers can look plausible even when they are not supported by a user's documents. PaperVault also needs page-level provenance, tenant isolation, predictable local operation, and a provider boundary that can later support model-backed generation.

## Decision

Persist overlapping text chunks as children of a specific page-aware extraction. Store embedding provider, model, dimensions, vector, and source hash with each chunk. Materialize chunks during document intelligence processing and lazily backfill older current extractions when their owner asks a question.

Keep question answering in a dedicated feature. Retrieval joins chunks through the current extraction and owning document, excludes non-ready documents, and returns bounded evidence. The default local answer provider is extractive and refuses when the evidence does not match enough question concepts. Every successful answer includes document and page citations.

Do not treat OpenSearch as the chunk source of truth. Database retrieval is bounded for current self-hosted vault sizes; a rebuildable chunk index can be added when scale requires it.

## Consequences

- Answers remain usable without an external model service.
- Existing documents become answerable without an offline backfill job.
- Reprocessing automatically moves retrieval to chunks belonging to the new current extraction.
- The local provider favors verifiability over conversational synthesis.
- Large vaults will require a dedicated chunk projection and embedding-version migration tooling.
