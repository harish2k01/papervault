# ADR 0027: Immutable Source Version Lifecycle

## Status

Accepted

## Context

Displaying an initial upload as "version 1" is not a versioning system. Long-lived
installations need to replace corrected scans, restore earlier sources, download any
retained source, and understand which extraction was produced from which binary.

## Decision

- Store filename, media type, hash, object reference, provenance, and current status on every source version.
- Permit exactly one current source version per document.
- Associate each text extraction with the source version it processed.
- Replace and restore by creating a new monotonically numbered current version; never mutate historical rows.
- Clear stale current metadata, analysis, embeddings, automatic tags, reminders, and extraction pointers before processing a new current source.
- Keep source objects referenced by restored versions and deduplicate object deletion during permanent document deletion.
- Compare versions by source hash and a bounded unified diff of their extracted text.

## Consequences

Version history is auditable and restoration does not rewrite the past. A restored
version may share an object-storage key with an earlier version, so deletion must work
on unique object references. Comparison depends on successful extraction for both
versions and is not a binary or visual PDF diff. Retention remains explicit and
unbounded until an operator-configurable policy is introduced.
