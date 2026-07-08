# ADR 0003: Use Provider Interfaces for OCR, AI, Search, and Storage

## Status

Accepted

## Context

PaperVault must support self-hosted deployments and optional hosted AI providers. OCR engines, embedding providers, LLM providers, search engines, and object stores will evolve independently.

## Decision

Integrations will be implemented behind explicit interfaces. Use cases depend on interfaces, not concrete provider clients. Concrete adapters live in infrastructure modules and are wired at the application boundary.

## Consequences

Adding a provider requires an adapter and tests rather than changes across the application. This introduces some upfront structure, but it protects long-term maintainability.
