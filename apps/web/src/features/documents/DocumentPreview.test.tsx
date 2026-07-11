import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getDocumentFile,
  getOcrTextBlocks,
  searchDocumentText,
} from "../../lib/api";
import { DocumentPreview } from "./DocumentPreview";

vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pdf-document">{children}</div>
  ),
  Page: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-page">Page {pageNumber}</div>
  ),
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("../../lib/api", () => ({
  getDocumentFile: vi.fn(),
  getOcrTextBlocks: vi.fn(),
  searchDocumentText: vi.fn(),
}));

describe("DocumentPreview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn().mockReturnValue("blob:document-preview"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.mocked(getDocumentFile).mockResolvedValue(new Blob(["pdf"]));
    vi.mocked(searchDocumentText).mockResolvedValue({
      query: "salary",
      total_matches: 1,
      page_mapping_available: true,
      matches: [
        {
          page_number: 2,
          before: "January",
          match: "salary",
          after: "was 1000",
        },
      ],
    });
    vi.mocked(getOcrTextBlocks).mockResolvedValue([
      {
        text: "salary",
        page_number: 2,
        left_ratio: 0.1,
        top_ratio: 0.2,
        width_ratio: 0.3,
        height_ratio: 0.05,
        confidence_score: 0.95,
      },
    ]);
  });

  it("searches extracted text and navigates to the matching page", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <DocumentPreview
          ocrGeometryAvailable
          document={{
            id: "document-1",
            owner_id: "user-1",
            title: "Salary statement",
            original_filename: "salary.pdf",
            content_type: "application/pdf",
            file_size_bytes: 1024,
            sha256_hash: "a".repeat(64),
            source_kind: "upload",
            status: "ready",
            document_type: "salary_slip",
            document_date: null,
            issuer: null,
            organization: null,
            review_status: "not_required",
            review_reasons: [],
            reviewed_at: null,
            reviewed_by_id: null,
            review_note: null,
            archived_at: null,
            created_at: "2026-07-11T00:00:00Z",
            updated_at: "2026-07-11T00:00:00Z",
          }}
        />
      </QueryClientProvider>,
    );

    const input = await screen.findByRole("searchbox", {
      name: "Search this document",
    });
    fireEvent.change(input, { target: { value: "salary" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(searchDocumentText).toHaveBeenCalledWith("document-1", "salary");
    });
    expect(await screen.findByText("1 match")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-page")).toHaveTextContent("Page 2");
    await waitFor(() => {
      expect(getOcrTextBlocks).toHaveBeenCalledWith("document-1", 2, "salary");
    });
    expect(await screen.findByTitle("salary")).toBeInTheDocument();
  });
});
