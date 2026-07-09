import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import {
  attachTag,
  createTag,
  getAuthConfig,
  getDocument,
  listDocuments,
  listTags,
} from "../../lib/api";
import { AppShell } from "./AppShell";

vi.mock("../../lib/api", () => ({
  archiveDocument: vi.fn(),
  attachTag: vi.fn(),
  buildOidcLoginUrl: vi
    .fn()
    .mockReturnValue("/auth/oidc/start?redirect_to=%2F"),
  clearStoredAccessToken: vi.fn(),
  createTag: vi.fn(),
  detachTag: vi.fn(),
  getAuthConfig: vi.fn(),
  getDocument: vi.fn(),
  getDocumentFile: vi.fn().mockResolvedValue(new Blob(["preview"])),
  getMe: vi.fn(),
  getStoredAccessToken: vi.fn().mockReturnValue(null),
  listDocumentTypes: vi.fn().mockResolvedValue([]),
  listDocuments: vi.fn().mockResolvedValue([]),
  listDuplicates: vi.fn().mockResolvedValue([]),
  listNotifications: vi.fn().mockResolvedValue([]),
  listRecentSearches: vi.fn().mockResolvedValue([]),
  listSavedSearches: vi.fn().mockResolvedValue([]),
  listTags: vi.fn().mockResolvedValue([]),
  loginAccount: vi.fn(),
  parseOidcCallbackHash: vi.fn().mockReturnValue(null),
  registerAccount: vi.fn(),
  saveSearch: vi.fn(),
  searchDocuments: vi.fn().mockResolvedValue([]),
  storeAccessToken: vi.fn(),
  updateDocument: vi.fn(),
  updateDocumentMetadata: vi.fn(),
  uploadDocument: vi.fn(),
}));

describe("AppShell", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn().mockReturnValue("blob:papervault-test"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.mocked(getAuthConfig).mockResolvedValue({
      dev_headers_enabled: true,
      local_auth_enabled: true,
      local_registration_enabled: true,
      oidc_configured: false,
    });
    vi.mocked(listDocuments).mockResolvedValue([]);
    vi.mocked(listTags).mockResolvedValue([]);
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

  it("attaches an existing suggested tag from the document panel", async () => {
    const createdAt = "2026-07-09T00:00:00.000Z";
    const document = {
      id: "document-1",
      owner_id: "user-1",
      title: "iPad Invoice",
      original_filename: "ipad-invoice.pdf",
      content_type: "application/pdf",
      file_size_bytes: 1024,
      sha256_hash: "a".repeat(64),
      source_kind: "upload",
      status: "ready",
      document_type: "invoice",
      document_date: null,
      issuer: null,
      organization: null,
      archived_at: null,
      created_at: createdAt,
      updated_at: createdAt,
    };
    vi.mocked(listDocuments).mockResolvedValueOnce([document]);
    vi.mocked(listTags).mockResolvedValueOnce([
      {
        id: "tag-1",
        name: "Warranty",
        slug: "warranty",
        color: null,
        description: null,
        source: "manual",
        created_at: createdAt,
      },
    ]);
    vi.mocked(getDocument).mockResolvedValue({
      document,
      ai_analysis: {
        summary: "Invoice for an iPad with warranty details.",
        keywords: ["invoice"],
        entities: [],
        suggested_tags: ["warranty"],
        category: "invoice",
        confidence_score: 0.86,
      },
      metadata: null,
      text_extraction: null,
      tags: [],
      timeline_events: [],
      versions: [],
    });
    vi.mocked(attachTag).mockResolvedValueOnce({ attached: true });

    renderAppShell();

    fireEvent.click(await screen.findByRole("button", { name: "Add warranty" }));

    await waitFor(() => {
      expect(attachTag).toHaveBeenCalledWith("document-1", "tag-1");
    });
    expect(createTag).not.toHaveBeenCalled();
  });
});

function renderAppShell() {
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
}
