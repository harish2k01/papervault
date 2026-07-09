import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { getAuthConfig } from "../../lib/api";
import { AppShell } from "./AppShell";

vi.mock("../../lib/api", () => ({
  buildOidcLoginUrl: vi
    .fn()
    .mockReturnValue("/auth/oidc/start?redirect_to=%2F"),
  clearStoredAccessToken: vi.fn(),
  getAuthConfig: vi.fn(),
  getDocument: vi.fn(),
  getDocumentFile: vi.fn(),
  getMe: vi.fn(),
  getStoredAccessToken: vi.fn().mockReturnValue(null),
  listDocuments: vi.fn().mockResolvedValue([]),
  listDuplicates: vi.fn().mockResolvedValue([]),
  listNotifications: vi.fn().mockResolvedValue([]),
  loginAccount: vi.fn(),
  parseOidcCallbackHash: vi.fn().mockReturnValue(null),
  registerAccount: vi.fn(),
  searchDocuments: vi.fn().mockResolvedValue([]),
  storeAccessToken: vi.fn(),
  uploadDocument: vi.fn(),
}));

describe("AppShell", () => {
  beforeEach(() => {
    vi.mocked(getAuthConfig).mockResolvedValue({
      dev_headers_enabled: true,
      local_auth_enabled: true,
      local_registration_enabled: true,
      oidc_configured: false,
    });
  });

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

    expect(
      await screen.findByRole("heading", { name: "Documents" }),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        "Search documents, tags, issuers, or questions",
      ),
    ).toBeInTheDocument();
  });

  it("renders OIDC sign-in when configured", async () => {
    vi.mocked(getAuthConfig).mockResolvedValueOnce({
      dev_headers_enabled: false,
      local_auth_enabled: true,
      local_registration_enabled: false,
      oidc_configured: true,
    });
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
      await screen.findByRole("button", { name: "Sign in with OIDC" }),
    ).toBeInTheDocument();
  });
});
