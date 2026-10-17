# ADR 0031: Independent document enrichment

## Context

Local CPU inference can occupy a worker for many minutes on a long document.
When OCR and model analysis share one serial consumer, later uploads cannot expose
their extracted contents until the preceding document finishes model inference.
This delays PaperVault's primary upload-and-find workflow even though keyword
retrieval does not need generated metadata or a summary.

## Decision

The homelab runs a dedicated ingestion consumer and a separate serial enrichment
consumer. Both use the same application image and the existing authenticated,
persistent Redis broker. Ingestion completes text extraction and search indexing
before publishing enrichment. The document is ready while analysis remains pending.
Single-consumer installations retain inline processing unless separation is enabled.

Each enrichment message carries document and extraction IDs. The service rejects
obsolete source IDs and successful duplicate deliveries before model invocation,
and rechecks source identity after inference. The task acknowledges after execution,
requeues on worker loss and retries unexpected infrastructure failures up to three
times. Invalid or unavailable model analysis becomes a review warning while the
extracted text and original remain available. Manual metadata remains authoritative.

## Consequences

New OCR work is independent of model latency, with one additional small worker pod.
Model throughput remains limited by the private CPU server. Broker outages and
exhausted infrastructure retries still require operational intervention; this is
not an exactly-once guarantee. A rollback to an image predating the enrichment task
requires draining its queue or retaining a compatible consumer. No additional
external service receives document contents.
