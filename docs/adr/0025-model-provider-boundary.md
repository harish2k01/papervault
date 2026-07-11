# ADR 0025: Model Provider Boundary

## Status

Accepted

## Context

Self-hosted installations need a credential-free local option and the ability to use
remote model APIs without coupling document processing or question answering to one
vendor. Analysis requires structured output, embeddings must match the search index
dimension, and generated answers must preserve PaperVault's evidence and citation
contract.

## Decision

- Keep deterministic `local` providers as the default.
- Support `ollama` and `openai_compatible` adapters for analysis, embeddings, and grounded answers.
- Configure each capability independently through environment variables.
- Parse model analysis and answer output as JSON and validate categories, confidence, citations, and vector dimensions at adapter boundaries.
- Keep credentials in deployment secrets and expose only non-secret provider, model, and reachability information to administrators.
- Store provider and model identifiers with generated analyses, embeddings, and chunks.

## Consequences

Operators can choose a fully local or remote model stack without changing application
code. Embedding model changes require an explicit dimension update and versioned
OpenSearch reindex. OpenAI-compatible endpoints vary in behavior, so evaluation
fixtures and provider health establish a minimum contract but do not replace
deployment-specific quality testing.
