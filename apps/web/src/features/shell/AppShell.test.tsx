import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppShell } from "./AppShell";

vi.mock("../../lib/api", () => ({
  clearStoredAccessToken: vi.fn(),
  getAuthConfig: vi.fn().mockResolvedValue({
    dev_headers_enabled: true,
    local_auth_enabled: true,
    local_registration_enabled: true,
    oidc_configured: false,
  }),
  getDocument: vi.fn(),
  getDocumentFile: vi.fn(),
  getMe: vi.fn(),
  getStoredAccessToken: vi.fn().mockReturnValue(null),
  listDocuments: vi.fn().mockResolvedValue([]),
  listDuplicates: vi.fn().mockResolvedValue([]),
  listNotifications: vi.fn().mockResolvedValue([]),
  loginAccount: vi.fn(),
  registerAccount: vi.fn(),
  searchDocuments: vi.fn().mockResolvedValue([]),
  storeAccessToken: vi.fn(),
  uploadDocument: vi.fn(),
}));

describe("AppShell", () => {
  it("renders the application shell", async () => {
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

    expect(await screen.findByRole("heading", { name: "Documents" })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        "Search documents, tags, issuers, or questions",
      ),
    ).toBeInTheDocument();
  });
});
