import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { documentIntelligence, retryDocumentIntelligence } from "../../lib/api";
import { DocumentIntelligence } from "./DocumentIntelligence";

vi.mock("../../lib/api", () => ({
  documentIntelligence: vi.fn(),
  retryDocumentIntelligence: vi.fn(),
}));

describe("DocumentIntelligence recovery", () => {
  it.each(["processing", "failed"])(
    "keeps saved findings visible when %s",
    async (status) => {
      vi.mocked(documentIntelligence).mockResolvedValue({
        status: "ready",
        page_count: 2,
        covered_pages: [1, 2],
        understanding: {
          status,
          covered_passages: 3,
          total_passages: 8,
          findings: [
            {
              kind: "condition",
              label: "Acceptance condition",
              value: "Payable after acceptance.",
              quote: "Payable after acceptance.",
              ordinal: 1,
              page_number: 2,
            },
          ],
        },
      });
      vi.mocked(retryDocumentIntelligence).mockResolvedValue({
        status: "queued",
      });
      const onPage = vi.fn();
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <DocumentIntelligence documentId="synthetic" onPage={onPage} />
        </QueryClientProvider>,
      );
      const details = screen
        .getByText("Document intelligence preview")
        .closest("details")!;
      details.open = true;
      fireEvent(details, new Event("toggle"));
      expect(
        await screen.findByText("Acceptance condition"),
      ).toBeInTheDocument();
      expect(screen.getByText(/3 of 8 passages analysed/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "View page 2" }));
      expect(onPage).toHaveBeenCalledWith(2);
      if (status === "failed") {
        expect(screen.getByText(/Completed work is saved/)).toBeInTheDocument();
        fireEvent.click(
          screen.getByRole("button", { name: "Retry document analysis" }),
        );
        await waitFor(() =>
          expect(retryDocumentIntelligence).toHaveBeenCalledWith("synthetic"),
        );
        expect(
          await screen.findByText("Retry queued. Saved work will resume."),
        ).toBeInTheDocument();
      } else {
        expect(
          screen.getByText(/Reading the remaining passages/),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole("button", { name: "Retry document analysis" }),
        ).not.toBeInTheDocument();
      }
    },
  );
});
