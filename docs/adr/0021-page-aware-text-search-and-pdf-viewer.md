# ADR 0021: Page-Aware Text Search And PDF Viewer

## Status

Accepted

## Context

The browser-native PDF iframe cannot provide a consistent search or highlighting contract, and PaperVault previously discarded page boundaries when it flattened extracted text. Global search could identify a document, but the document viewer could not reliably take the user to the relevant page. Scanned PDFs also need to use OCR text rather than depend on an embedded PDF text layer.

## Decision

Persist ordered page text as child rows of each text extraction. Keep the existing flattened text for AI analysis, embeddings, and global search. Add an owner-scoped literal text-search use case that returns page-aware, bounded excerpts as structured text fields.

Use React PDF and PDF.js for the web viewer. Load the viewer asynchronously, render one responsive page at a time, and highlight matches in the PDF text layer. For OCR-only PDFs, use persisted OCR page text for result navigation and excerpt highlighting even when the source PDF has no text layer.

Legacy extractions without page rows fall back to flattened-text matching and advertise that page mapping is unavailable.

## Consequences

- New embedded-text and OCR processing preserve page boundaries without duplicating source blobs.
- The initial web bundle does not include PDF.js; the viewer and worker are loaded only when needed.
- Search excerpts are safe to render because the API returns text segments rather than HTML.
- Existing documents need reprocessing before page navigation becomes available.
- Pixel-accurate highlights over scanned page images are not possible until OCR bounding boxes are stored; the viewer highlights the OCR result excerpt and navigates to the matching page instead.
