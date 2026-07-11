import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { DuplicatesWorkspace } from "./DuplicatesWorkspace";

it("requires explicit confirmation before resolving a similarity match", () => {
  const onMerge = vi.fn();
  render(
    <DuplicatesWorkspace
      groups={[
        {
          method: "ocr_similarity",
          confidence: 0.91,
          requires_confirmation: true,
          explanation: "OCR-tolerant text fingerprints are 92% similar.",
          signals: {
            text_similarity: 0.92,
            length_similarity: 0.98,
            shared_bands: 6,
          },
          documents: [
            {
              id: "document-1",
              title: "Receipt Original",
              original_filename: "receipt.pdf",
              sha256_hash: "a".repeat(64),
              document_type: "receipt",
              file_size_bytes: 42_000,
              page_count: 1,
              created_at: "2030-03-01T00:00:00Z",
            },
            {
              id: "document-2",
              title: "Receipt Scan",
              original_filename: "receipt-scan.pdf",
              sha256_hash: "b".repeat(64),
              document_type: "receipt",
              file_size_bytes: 48_000,
              page_count: 1,
              created_at: "2030-03-02T00:00:00Z",
            },
          ],
        },
      ]}
      isLoading={false}
      isResolving={false}
      isScanning={false}
      scanResult={undefined}
      error={null}
      onOpenDocument={vi.fn()}
      onMerge={onMerge}
      onScan={vi.fn()}
    />,
  );

  const archiveButton = screen.getByRole("button", {
    name: "Archive 1 duplicate",
  });
  expect(archiveButton).toBeDisabled();

  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /I reviewed these documents and confirm/,
    }),
  );
  expect(archiveButton).toBeEnabled();
  fireEvent.click(archiveButton);

  expect(onMerge).toHaveBeenCalledWith({
    keep_document_id: "document-1",
    duplicate_document_ids: ["document-2"],
    match_method: "ocr_similarity",
    confirm_non_exact: true,
  });
});
