# ADR 0006: Keep OCR Behind a Provider Interface

## Status

Accepted

## Context

OCR can be implemented in several ways: local Tesseract, OCRmyPDF, cloud OCR, or custom model-backed services. Self-hosted deployments often prefer local OCR, but those engines require system packages that should not be hidden inside core business logic.

## Decision

Represent OCR as a `TextExtractor` implementation. Phase 3 includes:

- `PypdfTextExtractor` for embedded PDF text.
- `UnavailableOcrTextExtractor` as an explicit fallback when OCR is not configured.
- `CompositeTextExtractor` that attempts embedded PDF text first and then falls back to OCR.

Phase 7 adds `TesseractCliTextExtractor`, which uses Poppler `pdftoppm` for scanned PDF page rendering and Tesseract for image OCR.

## Consequences

Scanned PDFs and images enter the same processing pipeline. Deployments can use the built-in Tesseract adapter, disable OCR explicitly, or add a remote OCR adapter behind the same interface.
