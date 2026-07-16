import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { listCollectionCandidates } from "../../lib/api";
import { CollectionsWorkspace } from "./CollectionsWorkspace";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    listCollectionCandidates: vi.fn(),
  };
});

const manualCollection = {
  id: "collection-1",
  name: "Household",
  slug: "household",
  description: "Shared household records",
  color: null,
  kind: "manual" as const,
  view_mode: "grid" as const,
  rule: {
    document_types: [],
    title_contains: null,
    issuer_contains: null,
    organization_contains: null,
    date_from: null,
    date_to: null,
    tags_any: [],
    include_archived: false,
  },
  document_count: 0,
  created_at: "2026-07-17T00:00:00Z",
  updated_at: "2026-07-17T00:00:00Z",
};

const candidate = {
  id: "document-1",
  title: "Device receipt",
  original_filename: "device-receipt.pdf",
  document_type: "receipt",
  document_date: "2026-07-01",
  issuer: "Example Store",
  organization: "Example Store",
  status: "ready",
  file_size_bytes: 120,
  created_at: "2026-07-01T00:00:00Z",
};

describe("CollectionsWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listCollectionCandidates).mockResolvedValue({
      documents: [candidate],
      total: 1,
    });
  });

  it("searches the vault and adds a document to a manual collection", async () => {
    const onAddDocument = vi.fn();

    renderWorkspace({
      collections: [manualCollection],
      selectedCollectionId: manualCollection.id,
      onAddDocument,
    });

    fireEvent.click(screen.getByRole("button", { name: "Add documents" }));
    expect(await screen.findByText("Device receipt")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(onAddDocument).toHaveBeenCalledWith(
      manualCollection.id,
      candidate.id,
    );
  });

  it("creates a dynamic collection from document rules", () => {
    const onCreateCollection = vi.fn();

    renderWorkspace({ onCreateCollection });
    fireEvent.click(
      screen.getAllByRole("button", { name: "New collection" })[0],
    );
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Invoices" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Dynamic/ }));
    fireEvent.change(screen.getByLabelText(/^Document type/), {
      target: { value: "invoice" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create collection" }));

    expect(onCreateCollection).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Invoices",
        kind: "dynamic",
        rule: expect.objectContaining({ document_types: ["invoice"] }),
      }),
    );
  });

  it("creates a smart tag from the shared rule builder", async () => {
    const onCreateSmartTag = vi.fn();

    renderWorkspace({ onCreateSmartTag });
    fireEvent.click(screen.getByRole("button", { name: /^Tags/ }));
    fireEvent.click(screen.getByRole("button", { name: "New smart tag" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Policies" },
    });
    fireEvent.change(screen.getByLabelText(/^Document type/), {
      target: { value: "insurance_policy" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create smart tag" }));

    await waitFor(() =>
      expect(onCreateSmartTag).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Policies",
          rule: expect.objectContaining({
            document_types: ["insurance_policy"],
            tags_any: [],
          }),
        }),
      ),
    );
  });
});

function renderWorkspace(
  overrides: Partial<Parameters<typeof CollectionsWorkspace>[0]> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CollectionsWorkspace
        collections={[]}
        selectedCollectionId={null}
        collectionDocuments={[]}
        collectionDocumentTotal={0}
        tags={[]}
        documentTypes={[
          { key: "invoice", label: "Invoice", metadata_fields: [] },
          {
            key: "insurance_policy",
            label: "Insurance Policy",
            metadata_fields: [],
          },
        ]}
        isLoading={false}
        isLoadingDocuments={false}
        isMutating={false}
        error={null}
        onSelectCollection={vi.fn()}
        onOpenDocument={vi.fn()}
        onCreateCollection={vi.fn()}
        onUpdateCollection={vi.fn()}
        onDeleteCollection={vi.fn()}
        onAddDocument={vi.fn()}
        onRemoveDocument={vi.fn()}
        onCreateTag={vi.fn()}
        onCreateSmartTag={vi.fn()}
        onUpdateSmartTag={vi.fn()}
        onRefreshSmartTag={vi.fn()}
        onDeleteTag={vi.fn()}
        {...overrides}
      />
    </QueryClientProvider>,
  );
}
