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

The selected private Qwen3 1.7B hybrid pipeline passes **8/8 cases**, including
**30/30 fields**, **18/18 summary concepts**, **8/8 tag facets**, and **22/22 noise-tag
checks**. Its [full report](evaluations/qwen3-17b-lines-v2.json) records actual
source evidence and remaining warnings. It also passes the three separate
[multi-page and conditional cases](evaluations/qwen3-17b-holdout-v2.json).

Measured on three CPU cores of an AMD Ryzen 5 2500U, single-page cases took
35.3–45.0 seconds; the two-page policy holdout took 67.2 seconds. These are observed development measurements, not
latency guarantees or a production accuracy estimate. Rejected quote-copying pilots
are retained under [evaluations/pilots](evaluations/pilots); their failures motivated
line selection and direct parsing of explicit labels. An 8/8 pipeline result does
not mean the small model alone extracted every field correctly: rejected attempts,
direct-label recovery, and optional-field failures remain visible in the reports.

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
endpoint to preserve the on-premises processing boundary. The homelab uses a private
cluster endpoint with cloud inference disabled.

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
fixtures. A local model is selected only after measuring quality, RAM, and latency
on available hardware.

## Grounded local analysis

The `grounded-lines-v2` contract sends numbered source lines to a private Ollama
endpoint. Structured output restricts categories and field names. The server builds
quotes from selected lines, normalizes dates using the configured locale, verifies
values against the source, and rejects invalid references. Explicit colon, tab, and
line-separated labels are also parsed directly. Conflicting values are withheld.
These checks establish source support, not that every field has the right meaning.

Version two requires both a typed value and line references for each selected fact.
It recognizes narrative joining/end dates, ordinal and month-first dates, explicit
annual compensation with lakh/crore units, and appointment clauses. Monthly pay is
not annualized. Explicit employer/employee definitions reject reversed parties;
entity names differing only in case do not create artificial conflicts. Strong
document headings can supply the initial category hint for fresh uploads. Supported
values still require literal source text or a defined date/amount normalization.

The separate `processing_narrative.json` set contains three synthetic employment
cases with 16 annotated fields, including legal party definitions, annexures,
signing versus joining dates, conditional termination and monthly-only pay. The
[deployed-v1 baseline](evaluations/narrative-v1-baseline.json) failed all three as
fresh generic uploads, including classification; this comparison measures the whole
pipeline, rather than isolating one parser change. It does not establish accuracy
on a representative production corpus.

```sh
python scripts/evaluate_processing.py --provider ollama \
  --corpus apps/api/tests/fixtures/processing_narrative.json --output narrative-quality.json
```

Reports include a source-code hash. `--resume` continues a matching partial report
only when provider, model identity, settings, source hash, corpus and completed case
order match. Completed quality failures remain in resumed results.

Summaries are extractive: selected passages, supported key fields, and conservative
critical-statement rules preserve source wording. They are not free-form generated
prose. Source evidence includes page numbers, with navigation to the original PDF.
Tags use supported topics and the classified document type; frequency-only words and
currency codes are excluded. Small-model omissions and unsupported attempts remain
visible as quality warnings. Classification confidence is never field accuracy.

Reprocessing invalidates stale generated outputs. Manual metadata and tags remain;
removed automatic tags are suppressed until explicitly reattached. Detected affirmative
cancellation, withdrawal, or termination statements hold automatic date reminders until
dates are manually confirmed. This is a conservative guard, not general legal-status
understanding; other wording can require human review.

The additional `processing_holdout.json` corpus exercises two-page cancellation,
conflicting totals, and a conditional cancellation clause. Reproduce it with:

```sh
python scripts/evaluate_processing.py --provider ollama \
  --corpus apps/api/tests/fixtures/processing_holdout.json --output holdout-quality.json
```

The recorded pilot reports retain failures from smaller contracts. They are rejected
candidates, not production quality claims. Full model identity, contract version,
context budget, corpus hash, warnings, evidence, and per-case latency accompany each
current benchmark. Synthetic text checks still do not prove real-world OCR accuracy,
table reconstruction, handwriting recognition, or reliable semantic retrieval.
