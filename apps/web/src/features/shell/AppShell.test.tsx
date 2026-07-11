import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import {
  attachTag,
  createTag,
  getAdminSettings,
  getAuthConfig,
  getDocument,
  getDocumentFile,
  getMe,
  getStoredAccessToken,
  listDuplicates,
  listDocuments,
  listNotifications,
  listTags,
  listUsers,
  mergeDuplicateDocuments,
  reprocessDocument,
  searchDocumentText,
  syncDocumentNotifications,
  updateNotificationStatus,
} from "../../lib/api";
import { AppShell } from "./AppShell";

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
  archiveDocument: vi.fn(),
  askQuestion: vi.fn(),
  attachTag: vi.fn(),
  buildOidcLoginUrl: vi
    .fn()
    .mockReturnValue("/auth/oidc/start?redirect_to=%2F"),
  clearStoredAccessToken: vi.fn(),
  createTag: vi.fn(),
  detachTag: vi.fn(),
  getAuthConfig: vi.fn(),
  getAdminSettings: vi.fn(),
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
  listUsers: vi.fn().mockResolvedValue([]),
  loginAccount: vi.fn(),
  mergeDuplicateDocuments: vi.fn(),
  parseOidcCallbackHash: vi.fn().mockReturnValue(null),
  registerAccount: vi.fn(),
  reprocessDocument: vi.fn(),
  saveSearch: vi.fn(),
  searchDocuments: vi.fn().mockResolvedValue([]),
  searchDocumentText: vi.fn().mockResolvedValue({
    query: "",
    total_matches: 0,
    page_mapping_available: true,
    matches: [],
  }),
  storeAccessToken: vi.fn(),
  syncDocumentNotifications: vi.fn().mockResolvedValue([]),
  updateDocument: vi.fn(),
  updateDocumentMetadata: vi.fn(),
  updateAdminSettings: vi.fn(),
  updateNotificationStatus: vi.fn(),
  updateUser: vi.fn(),
  uploadDocument: vi.fn(),
}));

describe("AppShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    vi.mocked(listDuplicates).mockResolvedValue([]);
    vi.mocked(listNotifications).mockResolvedValue([]);
    vi.mocked(listTags).mockResolvedValue([]);
    vi.mocked(syncDocumentNotifications).mockResolvedValue([]);
    vi.mocked(searchDocumentText).mockResolvedValue({
      query: "",
      total_matches: 0,
      page_mapping_available: true,
      matches: [],
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
      await screen.findByRole("heading", { name: "Add your first document." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Empty vault")).toBeInTheDocument();
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

    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "Add warranty" },
        { timeout: 3000 },
      ),
    );

    await waitFor(() => {
      expect(attachTag).toHaveBeenCalledWith("document-1", "tag-1");
    });
    expect(createTag).not.toHaveBeenCalled();
  });

  it("shows a bounded failed-document preview instead of loading the PDF viewer", async () => {
    const createdAt = "2026-07-09T17:21:39.000Z";
    const document = {
      id: "document-failed",
      owner_id: "user-1",
      title: "Statement 2026MTH04 609599319",
      original_filename: "Statement_2026MTH04_609599319.pdf",
      content_type: "application/pdf",
      file_size_bytes: 67584,
      sha256_hash: "b".repeat(64),
      source_kind: "upload",
      status: "failed",
      document_type: "generic_pdf",
      document_date: null,
      issuer: null,
      organization: null,
      archived_at: null,
      created_at: createdAt,
      updated_at: createdAt,
    };
    vi.mocked(listDocuments).mockResolvedValueOnce([document]);
    vi.mocked(getDocument).mockResolvedValueOnce({
      document,
      ai_analysis: null,
      metadata: {
        schema_name: "generic_pdf",
        schema_version: 1,
        data: {},
        confidence_score: null,
      },
      text_extraction: {
        status: "failed",
        source: "pdf",
        page_count: null,
        language: null,
        error_message: "Password required",
      },
      tags: [],
      timeline_events: [
        {
          id: "event-1",
          event_type: "document_uploaded",
          payload: {},
          occurred_at: createdAt,
        },
      ],
      versions: [
        {
          id: "version-1",
          version_number: 1,
          sha256_hash: document.sha256_hash,
          file_size_bytes: document.file_size_bytes,
          change_reason: null,
          created_by_id: "user-1",
          created_at: createdAt,
        },
      ],
    });
    vi.mocked(reprocessDocument).mockResolvedValueOnce({
      document: { ...document, status: "pending_processing" },
      processing_task_id: "task-retry",
    });

    renderAppShell();

    expect(await screen.findByText("Processing failed")).toBeInTheDocument();
    expect(await screen.findByText("Preview not ready")).toBeInTheDocument();
    expect(screen.queryByTitle(document.title)).not.toBeInTheDocument();
    expect(getDocumentFile).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Retry processing" }));
    await waitFor(() => {
      expect(reprocessDocument).toHaveBeenCalledWith(
        "document-failed",
        expect.any(Object),
      );
    });
  });

  it("shows administration settings only to administrators", async () => {
    vi.mocked(getStoredAccessToken).mockReturnValueOnce("admin-token");
    vi.mocked(getMe).mockResolvedValueOnce({
      id: "admin-1",
      email: "owner@example.com",
      display_name: "Owner",
      role: "admin",
      auth_provider: "local",
      is_active: true,
      created_at: "2026-07-11T00:00:00Z",
      last_login_at: null,
    });
    vi.mocked(getAdminSettings).mockResolvedValueOnce({
      local_registration_enabled: true,
      local_auth_enabled: true,
      oidc_configured: false,
      ai_provider: "local",
      embedding_provider: "local",
      ocr_provider: "tesseract",
      search_backend: "opensearch",
      search_index_enabled: true,
      max_upload_size_bytes: 104857600,
    });
    vi.mocked(listUsers).mockResolvedValueOnce([]);

    renderAppShell();

    const settingsButton = await screen.findByRole("button", {
      name: "Settings",
    });
    fireEvent.click(settingsButton);

    expect(
      await screen.findByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
  });

  it("dismisses a notification from the notifications workspace", async () => {
    const createdAt = "2026-07-09T17:21:39.000Z";
    const document = {
      id: "document-1",
      owner_id: "user-1",
      title: "Insurance Policy",
      original_filename: "insurance-policy.pdf",
      content_type: "application/pdf",
      file_size_bytes: 67584,
      sha256_hash: "c".repeat(64),
      source_kind: "upload",
      status: "ready",
      document_type: "insurance_policy",
      document_date: null,
      issuer: null,
      organization: null,
      archived_at: null,
      created_at: createdAt,
      updated_at: createdAt,
    };
    const notification = {
      id: "notification-1",
      document_id: document.id,
      kind: "expiry",
      status: "pending" as const,
      title: "Document expiry: Insurance Policy",
      message: "Insurance Policy has expiry on 2026-12-31.",
      due_date: "2026-12-31",
      payload: { source_field: "expiry_date" },
      created_at: createdAt,
    };
    vi.mocked(listDocuments).mockResolvedValueOnce([document]);
    vi.mocked(listNotifications).mockResolvedValueOnce([notification]);
    vi.mocked(getDocument).mockResolvedValueOnce({
      document,
      ai_analysis: null,
      metadata: null,
      text_extraction: null,
      tags: [],
      timeline_events: [],
      versions: [],
    });
    vi.mocked(updateNotificationStatus).mockResolvedValueOnce({
      ...notification,
      status: "dismissed",
    });

    renderAppShell();

    fireEvent.click(
      await screen.findByRole("button", { name: /Notifications/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Notifications" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(updateNotificationStatus).toHaveBeenCalledWith(
        "notification-1",
        "dismissed",
      );
    });
  });

  it("resolves an exact duplicate group from the duplicates workspace", async () => {
    const createdAt = "2026-07-09T17:21:39.000Z";
    const keptDocument = {
      id: "document-keep",
      owner_id: "user-1",
      title: "Invoice Original",
      original_filename: "invoice-original.pdf",
      content_type: "application/pdf",
      file_size_bytes: 67584,
      sha256_hash: "d".repeat(64),
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
    const duplicateDocument = {
      ...keptDocument,
      id: "document-duplicate",
      title: "Invoice Copy",
      original_filename: "invoice-copy.pdf",
    };
    vi.mocked(listDuplicates).mockResolvedValueOnce([
      {
        method: "sha256_hash",
        documents: [
          {
            id: keptDocument.id,
            title: keptDocument.title,
            original_filename: keptDocument.original_filename,
            sha256_hash: keptDocument.sha256_hash,
            created_at: keptDocument.created_at,
          },
          {
            id: duplicateDocument.id,
            title: duplicateDocument.title,
            original_filename: duplicateDocument.original_filename,
            sha256_hash: duplicateDocument.sha256_hash,
            created_at: duplicateDocument.created_at,
          },
        ],
      },
    ]);
    vi.mocked(mergeDuplicateDocuments).mockResolvedValueOnce({
      kept_document: keptDocument,
      archived_documents: [
        {
          ...duplicateDocument,
          status: "archived",
          archived_at: "2026-07-10T00:00:00.000Z",
        },
      ],
    });

    renderAppShell();

    fireEvent.click(await screen.findByRole("button", { name: /Duplicates/ }));
    expect(
      await screen.findByRole("heading", { name: "Duplicates" }),
    ).toBeInTheDocument();

    fireEvent.click(
      await screen.findByRole("button", { name: "Archive 1 duplicate" }),
    );

    await waitFor(() => {
      expect(mergeDuplicateDocuments).toHaveBeenCalledWith({
        keep_document_id: "document-keep",
        duplicate_document_ids: ["document-duplicate"],
      });
    });
  });

  it("refreshes document reminders from the selected document", async () => {
    const createdAt = "2026-07-09T17:21:39.000Z";
    const document = {
      id: "document-1",
      owner_id: "user-1",
      title: "Insurance Policy",
      original_filename: "insurance-policy.pdf",
      content_type: "application/pdf",
      file_size_bytes: 67584,
      sha256_hash: "e".repeat(64),
      source_kind: "upload",
      status: "ready",
      document_type: "insurance_policy",
      document_date: null,
      issuer: null,
      organization: null,
      archived_at: null,
      created_at: createdAt,
      updated_at: createdAt,
    };
    vi.mocked(listDocuments).mockResolvedValueOnce([document]);
    vi.mocked(getDocument).mockResolvedValueOnce({
      document,
      ai_analysis: null,
      metadata: {
        schema_name: "insurance_policy",
        schema_version: 1,
        data: { expiry_date: "2026-12-31" },
        confidence_score: null,
      },
      text_extraction: null,
      tags: [],
      timeline_events: [],
      versions: [],
    });
    vi.mocked(syncDocumentNotifications).mockResolvedValueOnce([]);

    renderAppShell();

    expect(
      await screen.findByRole("heading", { name: "Insurance Policy" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(syncDocumentNotifications).toHaveBeenCalledWith("document-1");
    });
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
