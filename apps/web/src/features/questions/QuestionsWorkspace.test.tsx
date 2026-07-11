import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { askQuestion } from "../../lib/api";
import { QuestionsWorkspace } from "./QuestionsWorkspace";

vi.mock("../../lib/api", () => ({
  askQuestion: vi.fn(),
}));

describe("QuestionsWorkspace", () => {
  it("renders a grounded answer and opens its citation", async () => {
    vi.mocked(askQuestion).mockResolvedValue({
      answered: true,
      answer: "Your net pay was INR 28,175.",
      confidence_score: 0.91,
      refusal_reason: null,
      citations: [
        {
          document_id: "document-1",
          document_title: "August Payslip",
          original_filename: "august.pdf",
          page_number: 1,
          snippet: "NET PAY INR 28,175",
          relevance_score: 0.94,
        },
      ],
    });
    const onOpenDocument = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <QuestionsWorkspace onOpenDocument={onOpenDocument} />
      </QueryClientProvider>,
    );

    fireEvent.change(
      screen.getByLabelText("Ask a question about your documents"),
      { target: { value: "What was my salary in August?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText("Your net pay was INR 28,175."),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /August Payslip - Page 1/ }),
    );
    expect(onOpenDocument).toHaveBeenCalledWith("document-1");
  });
});
