import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { askQuestion, questionCapabilities } from "../../lib/api";
import { QuestionsWorkspace } from "./QuestionsWorkspace";

vi.mock("../../lib/api", () => ({
  askQuestion: vi.fn(),
  questionCapabilities: vi
    .fn()
    .mockResolvedValue({ structured_retrieval: "disabled" }),
}));

describe("QuestionsWorkspace", () => {
  it("opts into semantic retrieval and labels source spans without a certainty percentage", async () => {
    vi.mocked(questionCapabilities).mockResolvedValue({
      structured_retrieval: "preview",
    });
    vi.mocked(askQuestion).mockResolvedValue({
      answered: true,
      answer: "Only after acceptance.",
      confidence_score: 0,
      answer_kind: "source_span",
      citations: [],
      refusal_reason: null,
    });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <QueryClientProvider client={client}>
        <QuestionsWorkspace onOpenDocument={vi.fn()} />
      </QueryClientProvider>,
    );
    fireEvent.click(
      await screen.findByLabelText("Try semantic retrieval preview"),
    );
    fireEvent.change(
      screen.getByLabelText("Ask a question about your documents"),
      { target: { value: "When is payment due?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    expect(
      await screen.findByText("Only after acceptance."),
    ).toBeInTheDocument();
    expect(askQuestion).toHaveBeenCalledWith(
      "When is payment due?",
      "candidate",
    );
    expect(
      screen.getByText("Exact source quote · preview"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0% confidence/)).not.toBeInTheDocument();
  });

  it("renders a grounded answer and opens its citation", async () => {
    vi.mocked(askQuestion).mockResolvedValue({
      answered: true,
      answer: "Your net pay was INR 12,000.",
      confidence_score: 0.91,
      refusal_reason: null,
      citations: [
        {
          document_id: "document-1",
          document_title: "Synthetic Payroll Statement",
          original_filename: "synthetic-payroll.pdf",
          page_number: 1,
          snippet: "NET PAY INR 12,000",
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
      { target: { value: "What was the net pay in my latest payslip?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText("Your net pay was INR 12,000."),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: /Synthetic Payroll Statement - Page 1/,
      }),
    );
    expect(onOpenDocument).toHaveBeenCalledWith("document-1");
  });
});
