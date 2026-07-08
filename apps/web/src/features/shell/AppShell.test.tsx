import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppShell } from "./AppShell";

vi.mock("../../lib/api", () => ({
  getDocument: vi.fn(),
  getDocumentFile: vi.fn(),
  listDocuments: vi.fn().mockResolvedValue([]),
  listDuplicates: vi.fn().mockResolvedValue([]),
  listNotifications: vi.fn().mockResolvedValue([]),
  searchDocuments: vi.fn().mockResolvedValue([]),
  uploadDocument: vi.fn(),
}));

describe("AppShell", () => {
  it("renders the application shell", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AppShell />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Documents" }),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        "Search documents, tags, issuers, or questions",
      ),
    ).toBeInTheDocument();
  });
});
