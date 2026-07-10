# ADR 0010: Use Local Tesseract for the First OCR Adapter

## Status

Accepted

## Context

PaperVault must process scanned PDFs and uploaded images. OCR can be local, remote, or model-backed. A hosted OCR service would reduce system package complexity, but it would weaken the default self-hosted story and add privacy concerns for personal documents.

## Decision

The local OCR adapter sits behind the existing `TextExtractor` interface:

- `TesseractCliTextExtractor` runs Tesseract through a command runner.
- Scanned PDFs are rendered to page images with Poppler `pdftoppm`.
- Images are passed directly to Tesseract.
- OCR language, timeout, DPI, page limit, command paths, and page segmentation mode are configurable.
- The Celery worker image installs `tesseract-ocr` and `poppler-utils`.
- The unavailable OCR adapter remains available for deployments that disable OCR.

## Consequences

The default containerized worker can OCR scanned documents without proprietary services. The trade-off is that OCR quality and language coverage depend on installed Tesseract language packs, and OCR consumes worker CPU. Remote OCR providers, OCRmyPDF, or model-backed OCR can still be added behind the same interface later.
