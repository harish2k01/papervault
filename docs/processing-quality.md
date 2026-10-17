# Processing quality

PaperVault distinguishes successful execution from useful document understanding.
The initial quality corpus contains eight synthetic text cases with annotated facts,
summary concepts, contradiction checks, and tag expectations. It includes column-based
invoices and statements, cancelled coverage, a withdrawn offer, medical negation,
zero net pay, and minimum versus total card payments.

## Current baseline

The deterministic `local:rules-v1` provider passes all expectations for **1 of 8 cases**.
The recorded [baseline report](evaluations/rules-v1.json) contains each expected and
actual value. Results on this small synthetic corpus are:

| Check | Passed / annotated checks |
| --- | --- |
| Document classification | 8 / 8 |
| Normalized metadata fields | 22 / 30 |
| Required summary concepts | 10 / 18 |
| Useful tag facets | 8 / 8 |
| Avoiding annotated unhelpful tags | 11 / 22 |
| Avoiding specific contradictory summary claims | 7 / 7 |

Correct classification does not establish correct metadata or summary completeness.
The report preserves classification confidence separately and never uses it to score
factual checks. A generic summary can avoid the listed contradictions while still
omitting critical information; both checks must pass.

## Reproducing the benchmark

Install the backend with its development dependencies. From the repository root:

```sh
python scripts/evaluate_processing.py --output processing-quality.json
```

The default command exits **1** when any annotated expectation fails, including a
provider error. `--report-only` writes the same failing result but exits successfully
so CI can retain a baseline artifact. A green CI report-generation step does not
mean the provider passed the quality benchmark.

To compare a locally hosted model, configure `PAPERVAULT_OLLAMA_BASE_URL` and
`PAPERVAULT_OLLAMA_CHAT_MODEL`, then run:

```sh
python scripts/evaluate_processing.py --provider ollama --output ollama-quality.json
```

The benchmark supports only the deterministic local provider and Ollama. Corpus text
goes to the configured Ollama endpoint when selected; deployments must use an internal
endpoint to preserve the on-premises processing boundary. No hosted provider is enabled
by this milestone.

## Page-aware PDF extraction

PDF inspection examines raster drawing size and embedded text for each page. A page
requires OCR when it has no embedded text, substantial raster content (20% of page
area), sparse embedded text with raster content (at least 2% and fewer than 40
alphanumeric characters), or excessive replacement characters. Image-bearing Form
XObjects are included conservatively. Small logos on otherwise digital pages do not
automatically force OCR. Pages without text or painted content are identified as
blank rather than treated as failed scanned attachments.

For pages requiring OCR, native text remains intact and additional OCR lines are
appended, with duplicate lines removed. Other digital pages retain their original
text. Missing required OCR output, partial page coverage, and OCR that only repeats
a sparse footer are failures rather than successful extraction. Native text is retained
in the failed extraction for inspection.

These thresholds route work; they do not certify recognition accuracy. Form bounds
can overestimate raster coverage, photos can trigger OCR, and native/OCR line merging
does not reconstruct table relationships or exact reading order. Required OCR still
renders the PDF as a whole and obeys the existing page limit. Per-region parsing,
selective page rendering, table reconstruction, and improved multilingual OCR remain
follow-up work.

## Acceptance for the local processing rebuild

The text benchmark is an initial regression set, not a production accuracy estimate.
Phrase alternatives are transparent checks, not an independent semantic judge; they
can reject valid paraphrases and do not detect every unsupported claim. Unannotated
fields and claims require human review. The corpus does not measure photographed
documents, handwriting, semantic retrieval, or processing latency.

The next evaluation must add representative local documents with per-page expected
text, field values, evidence locations, important summary facts, and retrieval queries.
Any replacement parser/model must be evaluated on held-out layouts, not just these
fixtures. A local model is selected only after measuring quality, peak RAM, and latency
on available hardware. Subsequent work must add field-level source evidence, preserve
manual corrections during reprocessing, and expose incomplete or uncertain stages to
the user before considering generated results trustworthy.
