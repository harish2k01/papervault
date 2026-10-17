# Source-grounded local analysis

## Context

Successful OCR and classification did not establish useful document understanding.
The lexical baseline missed column layouts and consequential status facts. Small CPU
models also omitted fields and produced incorrect quote references despite high
self-reported confidence. Document contents must stay inside the deployment.

## Decision

Use a private Ollama service with cloud inference disabled and a digest-verified
Qwen3 1.7B model. Analysis uses bounded windows across all source pages. The model
selects numbered lines; the server derives quotes, reads explicit labelled values,
normalizes types and locale-specific dates, and rejects unsupported output. Repeated
conflicting values are withheld for review. Summaries preserve actual source wording.

Persist field and summary evidence, coverage, and warnings. The UI polls while
analysis is pending and provides navigation from evidence to the original page.
Classification confidence is labelled separately from field accuracy.

Human metadata and tag decisions survive reprocessing. Removed automatic tags have
durable suppression records, including recovery from historical human tag events.
Affirmative cancellation/withdrawal/termination statements suppress automatic date
reminders from generated metadata until dates are explicitly confirmed by editing.

## Consequences

The pipeline can recover explicit facts even when the small model omits them, and
users can inspect where retained facts came from. Source support cannot prove semantic
correctness, completeness, current legal status, or an OCR transcription's accuracy.
Rules recognize only a subset of consequential wording. Tables and complex layouts
still need review. Existing model adapters remain configurable; only the private
homelab endpoint is enabled by the deployment profile.

CPU throughput is limited. Ollama serves one request at a time and the homelab worker
has concurrency one. Model failures leave extracted text searchable and expose a
review reason. Model weights and runtime identities are retained separately from
immutable application image identities. Synthetic benchmark receipts document the
measured improvement and rejected pilot contracts; they are not production accuracy
estimates or evidence of semantic retrieval.
