# ADR 0028: Explainable Duplicate Similarity

## Status

Accepted

## Context

Binary SHA-256 hashes identify byte-for-byte copies but miss re-exported PDFs, rescans,
and OCR variants. Comparing every document pair on every request does not scale, and
automatically merging approximate matches risks hiding distinct records with similar
templates.

## Decision

PaperVault persists one versioned fingerprint for each document's current successful
text extraction. The fingerprint contains a normalized-text SHA-256 hash and a
deterministic 32-value MinHash signature over token shingles. Eight indexed
locality-sensitive bands generate a small candidate set; full signature and relative
length scores are calculated only for those candidates.

Candidates are labeled as exact file, exact normalized text, content similarity, or
OCR similarity. Results expose confidence and component signals. Exact-file matches
may be archived directly. Every other method requires explicit user confirmation, and
the API revalidates current fingerprints and configured thresholds inside the merge
command before archiving redundant records. Source objects are retained.

Fingerprints are generated during worker processing and removed immediately when a
new source version is activated. Existing libraries are backfilled through an explicit,
bounded refresh command.

## Consequences

- Candidate generation grows approximately linearly with fingerprints and bands rather
  than quadratically with document count.
- OCR variants can be found without weakening exact-file guarantees.
- Similarity remains probabilistic and requires review; thresholds need corpus-specific
  evaluation before operators lower the defaults.
- Fingerprint algorithm changes require a version bump and bounded backfill.
