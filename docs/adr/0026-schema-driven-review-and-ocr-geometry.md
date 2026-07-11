# ADR 0026: Schema-Driven Review And OCR Geometry

## Status

Accepted

## Context

Document extraction needs to support many document families without embedding field
rules in HTTP handlers or provider adapters. Extracted values can be ambiguous across
locales, and model confidence alone does not prove that required metadata is complete.
OCR-only documents also need precise search highlights at different viewer sizes.

## Decision

- Keep document types and typed metadata fields in the domain registry.
- Normalize provider and manual metadata through one domain service before persistence.
- Support locale-aware dates, currencies, numbers, booleans, and object-list fields.
- Persist explicit review state and machine-readable review reasons on each document.
- Treat approval as an owner-scoped lifecycle command with reviewer provenance and a timeline event.
- Persist Tesseract word coordinates as normalized ratios attached to an extraction.
- Query OCR blocks by current extraction, page, owner, and optional search terms.

## Consequences

New document types can add typed fields without a database migration, and every
provider shares the same validation and review behavior. Invalid source values remain
available for correction instead of being silently discarded. Review state is a
workflow signal, not proof of document authenticity. Word-level OCR geometry increases
row count and storage usage, so responses are page-scoped and bounded; older OCR
extractions require reprocessing to gain geometry.
