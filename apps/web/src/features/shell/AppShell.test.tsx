import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import {
  type DocumentDetail,
  type DocumentItem,
  attachTag,
  createTag,
  getAdminSettings,
  getAuthConfig,
  getDocument,
  getDocumentFile,
  getMe,
  getProviderHealth,
  getStoredAccessToken,
  listDuplicates,
  listDocuments,
  listNotifications,
  listReviewQueue,
  listTags,
  listUsers,
  mergeDuplicateDocuments,
  reprocessDocument,
  searchDocuments,
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
  addDocumentToCollection: vi.fn(),
  archiveDocument: vi.fn(),
  askQuestion: vi.fn(),
  attachTag: vi.fn(),
  buildOidcLoginUrl: vi
    .fn()
    .mockReturnValue("/auth/oidc/start?redirect_to=%2F"),
  clearStoredAccessToken: vi.fn(),
  createCollection: vi.fn(),
  createSmartTag: vi.fn(),
  createTag: vi.fn(),
  deleteCollection: vi.fn(),
  deleteDocument: vi.fn(),
  deleteTag: vi.fn(),
  deleteUser: vi.fn(),
  detachTag: vi.fn(),
  downloadDocumentFile: vi.fn(),
  downloadDocumentVersion: vi.fn(),
  getAuthConfig: vi.fn(),
  getAdminSettings: vi.fn(),
  getDocument: vi.fn(),
  getDocumentFile: vi.fn().mockResolvedValue(new Blob(["preview"])),
  getMe: vi.fn(),
  getProviderHealth: vi.fn().mockResolvedValue({ checks: [] }),
  getStoredAccessToken: vi.fn().mockReturnValue(null),
  listDocumentTypes: vi.fn().mockResolvedValue([]),
  listDocuments: vi.fn().mockResolvedValue([]),
  listCollectionDocuments: vi
    .fn()
    .mockResolvedValue({ documents: [], total: 0 }),
  listCollections: vi.fn().mockResolvedValue([]),
  listDuplicates: vi.fn().mockResolvedValue([]),
  listNotifications: vi.fn().mockResolvedValue([]),
  listReviewQueue: vi.fn().mockResolvedValue([]),
  listRecentSearches: vi.fn().mockResolvedValue([]),
  listSavedSearches: vi.fn().mockResolvedValue([]),
  listTags: vi.fn().mockResolvedValue([]),
  listUsers: vi.fn().mockResolvedValue([]),
  listVaultTimeline: vi.fn().mockResolvedValue([]),
  loginAccount: vi.fn(),
  mergeDuplicateDocuments: vi.fn(),
  refreshDuplicateFingerprints: vi.fn().mockResolvedValue({
    scanned: 0,
    updated: 0,
    skipped: 0,
  }),
  refreshSmartTag: vi.fn(),
  parseOidcCallbackHash: vi.fn().mockReturnValue(null),
  registerAccount: vi.fn(),
  reprocessDocument: vi.fn(),
  replaceDocumentSource: vi.fn(),
  removeDocumentFromCollection: vi.fn(),
  restoreDocumentVersion: vi.fn(),
  compareDocumentVersions: vi.fn(),
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
  updateCollection: vi.fn(),
  updateDocumentMetadata: vi.fn(),
  updateAdminSettings: vi.fn(),
  updateNotificationStatus: vi.fn(),
  updateSmartTagRule: vi.fn(),
  updateDocumentReview: vi.fn(),
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
    vi.mocked(getMe).mockResolvedValue({
      id: "dev-user",
      email: "local@papervault.dev",
      display_name: null,
      role: "user",
      auth_provider: "development",
      is_active: true,
      created_at: "2026-07-11T00:00:00Z",
      last_login_at: null,
    });
    vi.mocked(getProviderHealth).mockResolvedValue({ checks: [] });
    vi.mocked(listDuplicates).mockResolvedValue([]);
    vi.mocked(listNotifications).mockResolvedValue([]);
    vi.mocked(listReviewQueue).mockResolvedValue([]);
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
      await screen.findByRole(
        "heading",
        { name: "Add your first document" },
        { timeout: 5_000 },
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Your paperwork, beautifully in order.",
      }),
    ).toBeInTheDocument();
  });

  it("refreshes a queued document until extracted text and preview become available", async () => {
    const document: DocumentItem = {
      id: "polling-document",
      owner_id: "dev-user",
      title: "Processing receipt",
      original_filename: "receipt.pdf",
      content_type: "application/pdf",
      file_size_bytes: 512,
      sha256_hash: "c".repeat(64),
      source_kind: "upload",
      status: "pending_processing",
      document_type: "generic_pdf",
      document_date: null,
      issuer: null,
      organization: null,
      review_status: "pending",
      review_reasons: [],
      reviewed_at: null,
      reviewed_by_id: null,
      review_note: null,
      archived_at: null,
      created_at: "2026-10-16T12:00:00Z",
      updated_at: "2026-10-16T12:00:00Z",
    };
    const detail: DocumentDetail = {
      document,
      ai_analysis: null,
      metadata: null,
      text_extraction: null,
      tags: [],
      timeline_events: [],
      versions: [],
    };
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(getDocument)
      .mockResolvedValueOnce(detail)
      .mockResolvedValueOnce({
        ...detail,
        document: {
          ...document,
          status: "ready",
          review_reasons: ["analysis_pending:metadata"],
        },
      })
      .mockResolvedValue({
        ...detail,
        document: {
          ...document,
          status: "ready",
          review_reasons: [
            "unsupported_metadata:provider",
            "unsupported_metadata:policy_number",
            "unsupported_metadata:coverage",
            "status_change:reminders",
          ],
        },
        ai_analysis: {
          provider: "ollama",
          model: "local",
          summary: "Net Pay: INR 0",
          keywords: [],
          entities: [],
          suggested_tags: [],
          category: "salary_slip",
          confidence_score: 0.9,
          summary_evidence: [{ page_number: 2, quote: "Net Pay: INR 0" }],
        },
      });
    renderAppShell();
    await openDocumentFromLibrary("Processing receipt");
    expect(getDocumentFile).not.toHaveBeenCalled();
    await waitFor(
      () => expect(getDocumentFile).toHaveBeenCalledWith("polling-document"),
      { timeout: 4000 },
    );
    const evidence = await screen.findByText(
      "Source evidence",
      {},
      { timeout: 6000 },
    );
    fireEvent.click(evidence);
    fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
    await waitFor(() =>
      expect(screen.getByTestId("pdf-page")).toHaveTextContent("Page 2"),
    );
    expect(getDocument).toHaveBeenCalledTimes(3);
    expect(
      screen.getByText(/Status change found; confirm dates in Details/),
    ).toBeInTheDocument();
  }, 10000);

  it("searches extracted content without requiring AI and shows the matching passage", async () => {
    vi.mocked(searchDocuments).mockResolvedValueOnce([
      {
        document_id: "receipt-1",
        title: "Service receipt",
        original_filename: "receipt.pdf",
        document_type: "receipt",
        status: "ready",
        summary: null,
        created_at: "2026-10-16T12:00:00Z",
        score: 1,
        highlights: ["Replacement compressor reference ZXQ918273"],
      },
    ]);
    renderAppShell();
    fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
    fireEvent.change(
      screen.getByRole("searchbox", { name: "Search documents" }),
      {
        target: { value: "ZXQ918273" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(
      await screen.findByText("Replacement compressor reference ZXQ918273"),
    ).toBeInTheDocument();
    expect(searchDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ query: "ZXQ918273", mode: "keyword" }),
    );
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

    await openDocumentFromLibrary("iPad Invoice");

    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "Add Warranty" },
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
      title: "Example account statement",
      original_filename: "example-account-statement.pdf",
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

    await openDocumentFromLibrary("Example account statement");

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
      answer_provider: "local",
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
        confidence: 1,
        requires_confirmation: false,
        explanation: "Files have identical SHA-256 hashes.",
        signals: {
          text_similarity: 1,
          length_similarity: 1,
          shared_bands: 8,
        },
        documents: [
          {
            id: keptDocument.id,
            title: keptDocument.title,
            original_filename: keptDocument.original_filename,
            sha256_hash: keptDocument.sha256_hash,
            document_type: keptDocument.document_type,
            file_size_bytes: keptDocument.file_size_bytes,
            page_count: 1,
            created_at: keptDocument.created_at,
          },
          {
            id: duplicateDocument.id,
            title: duplicateDocument.title,
            original_filename: duplicateDocument.original_filename,
            sha256_hash: duplicateDocument.sha256_hash,
            document_type: duplicateDocument.document_type,
            file_size_bytes: duplicateDocument.file_size_bytes,
            page_count: 1,
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
      await screen.findByRole("heading", { name: "Duplicate review" }),
    ).toBeInTheDocument();

    fireEvent.click(
      await screen.findByRole("button", { name: "Archive 1 duplicate" }),
    );

    await waitFor(() => {
      expect(mergeDuplicateDocuments).toHaveBeenCalledWith({
        keep_document_id: "document-keep",
        duplicate_document_ids: ["document-duplicate"],
        match_method: "sha256_hash",
        confirm_non_exact: false,
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

    await openDocumentFromLibrary("Insurance Policy");

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

async function openDocumentFromLibrary(title: string) {
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  fireEvent.click(
    await screen.findByRole("button", { name: new RegExp(title) }),
  );
}
