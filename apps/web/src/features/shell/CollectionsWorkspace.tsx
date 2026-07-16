import { type ReactNode, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Folder,
  FolderKanban,
  Grid2X2,
  List,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import {
  CollectionDocument,
  CollectionItem,
  CollectionKind,
  CollectionView,
  DocumentRule,
  DocumentTypeDefinition,
  TagItem,
  listCollectionCandidates,
} from "../../lib/api";
import { cn, humanizeLabel } from "../../lib/utils";

type CollectionInput = {
  name: string;
  description?: string | null;
  color?: string | null;
  kind: CollectionKind;
  view_mode: CollectionView;
  rule: DocumentRule;
};

const emptyRule: DocumentRule = {
  document_types: [],
  title_contains: null,
  issuer_contains: null,
  organization_contains: null,
  date_from: null,
  date_to: null,
  tags_any: [],
  include_archived: false,
};

export function CollectionsWorkspace({
  collections,
  selectedCollectionId,
  collectionDocuments,
  collectionDocumentTotal,
  tags,
  documentTypes,
  isLoading,
  isLoadingDocuments,
  isMutating,
  error,
  onSelectCollection,
  onOpenDocument,
  onCreateCollection,
  onUpdateCollection,
  onDeleteCollection,
  onAddDocument,
  onRemoveDocument,
  onCreateTag,
  onCreateSmartTag,
  onUpdateSmartTag,
  onRefreshSmartTag,
  onDeleteTag,
}: {
  collections: CollectionItem[];
  selectedCollectionId: string | null;
  collectionDocuments: CollectionDocument[];
  collectionDocumentTotal: number;
  tags: TagItem[];
  documentTypes: DocumentTypeDefinition[];
  isLoading: boolean;
  isLoadingDocuments: boolean;
  isMutating: boolean;
  error: string | null;
  onSelectCollection: (collectionId: string | null) => void;
  onOpenDocument: (documentId: string) => void;
  onCreateCollection: (input: CollectionInput) => void;
  onUpdateCollection: (
    collectionId: string,
    input: Partial<Omit<CollectionInput, "kind">>,
  ) => void;
  onDeleteCollection: (collectionId: string, name: string) => void;
  onAddDocument: (collectionId: string, documentId: string) => void;
  onRemoveDocument: (collectionId: string, documentId: string) => void;
  onCreateTag: (input: {
    name: string;
    description?: string | null;
    color?: string | null;
  }) => void;
  onCreateSmartTag: (input: {
    name: string;
    description?: string | null;
    color?: string | null;
    rule: DocumentRule;
  }) => void;
  onUpdateSmartTag: (tagId: string, rule: DocumentRule) => void;
  onRefreshSmartTag: (tagId: string) => void;
  onDeleteTag: (tagId: string, name: string) => void;
}) {
  const [section, setSection] = useState<"collections" | "tags">("collections");
  const [editor, setEditor] = useState<
    "collection" | "tag" | "smart-tag" | null
  >(null);
  const [editingCollection, setEditingCollection] =
    useState<CollectionItem | null>(null);
  const [editingSmartTag, setEditingSmartTag] = useState<TagItem | null>(null);
  const [showAddDocuments, setShowAddDocuments] = useState(false);
  const [candidateQuery, setCandidateQuery] = useState("");
  const [submittedCandidateQuery, setSubmittedCandidateQuery] = useState("");
  const selectedCollection =
    collections.find((collection) => collection.id === selectedCollectionId) ??
    null;
  const candidateDocumentsQuery = useQuery({
    queryKey: [
      "collections",
      "candidates",
      selectedCollection?.id,
      submittedCandidateQuery,
    ],
    queryFn: () =>
      listCollectionCandidates(selectedCollection!.id, submittedCandidateQuery),
    enabled:
      showAddDocuments &&
      selectedCollection !== null &&
      selectedCollection.kind === "manual",
  });

  useEffect(() => {
    setShowAddDocuments(false);
    setCandidateQuery("");
    setSubmittedCandidateQuery("");
  }, [selectedCollectionId]);

  function openCollectionEditor(collection: CollectionItem | null = null) {
    setEditingCollection(collection);
    setEditingSmartTag(null);
    setEditor("collection");
  }

  function openSmartTagEditor(tag: TagItem | null = null) {
    setEditingSmartTag(tag);
    setEditingCollection(null);
    setEditor("smart-tag");
  }

  function openTagEditor() {
    setEditingSmartTag(null);
    setEditingCollection(null);
    setEditor("tag");
  }

  function closeEditor() {
    setEditor(null);
    setEditingCollection(null);
    setEditingSmartTag(null);
  }

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-4 xl:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Collections</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Organize the vault without moving or duplicating source files.
            </p>
          </div>
          <div className="flex gap-2">
            {section === "tags" ? (
              <Button variant="outline" type="button" onClick={openTagEditor}>
                <Tag className="h-4 w-4" aria-hidden="true" />
                New tag
              </Button>
            ) : null}
            <Button
              type="button"
              onClick={() =>
                section === "collections"
                  ? openCollectionEditor()
                  : openSmartTagEditor()
              }
            >
              {section === "collections" ? (
                <Plus className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              )}
              {section === "collections" ? "New collection" : "New smart tag"}
            </Button>
          </div>
        </div>
        <div className="mt-4 flex gap-1">
          <SectionTab
            active={section === "collections"}
            label="Collections"
            count={collections.length}
            onClick={() => {
              setSection("collections");
              closeEditor();
            }}
          />
          <SectionTab
            active={section === "tags"}
            label="Tags"
            count={tags.length}
            onClick={() => {
              setSection("tags");
              closeEditor();
            }}
          />
        </div>
      </header>

      {error ? (
        <p
          className="mx-5 mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100 xl:mx-8"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {editor === "collection" ? (
          <CollectionEditor
            key={editingCollection?.id ?? "new-collection"}
            collection={editingCollection}
            documentTypes={documentTypes}
            tags={tags}
            disabled={isMutating}
            onCancel={closeEditor}
            onSubmit={(input) => {
              if (editingCollection) {
                onUpdateCollection(editingCollection.id, {
                  name: input.name,
                  description: input.description,
                  color: input.color,
                  view_mode: input.view_mode,
                  rule:
                    editingCollection.kind === "dynamic"
                      ? input.rule
                      : undefined,
                });
              } else {
                onCreateCollection(input);
              }
              closeEditor();
            }}
          />
        ) : editor === "tag" ? (
          <TagEditor
            disabled={isMutating}
            onCancel={closeEditor}
            onSubmit={(input) => {
              onCreateTag(input);
              closeEditor();
            }}
          />
        ) : editor === "smart-tag" ? (
          <SmartTagEditor
            key={editingSmartTag?.id ?? "new-smart-tag"}
            tag={editingSmartTag}
            documentTypes={documentTypes}
            disabled={isMutating}
            onCancel={closeEditor}
            onSubmit={(input) => {
              if (editingSmartTag) {
                onUpdateSmartTag(editingSmartTag.id, input.rule);
              } else {
                onCreateSmartTag(input);
              }
              closeEditor();
            }}
          />
        ) : section === "tags" ? (
          <TagsPanel
            tags={tags}
            isLoading={isLoading}
            isMutating={isMutating}
            onEdit={openSmartTagEditor}
            onRefresh={onRefreshSmartTag}
            onDelete={onDeleteTag}
          />
        ) : (
          <div className="grid min-h-full xl:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="border-b border-border bg-card p-4 xl:border-b-0 xl:border-r">
              <button
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm",
                  selectedCollection === null
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                type="button"
                onClick={() => onSelectCollection(null)}
              >
                <FolderKanban className="h-4 w-4" aria-hidden="true" />
                <span className="flex-1">All collections</span>
                <span className="text-xs">{collections.length}</span>
              </button>
              <div className="mt-3 space-y-1">
                {collections.map((collection) => (
                  <button
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                      selectedCollectionId === collection.id
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                    key={collection.id}
                    type="button"
                    onClick={() => onSelectCollection(collection.id)}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{
                        backgroundColor:
                          collection.color ?? "hsl(var(--primary))",
                      }}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      {collection.name}
                    </span>
                    <span className="text-xs opacity-75">
                      {collection.document_count}
                    </span>
                  </button>
                ))}
              </div>
            </aside>

            <div className="min-w-0 p-5 xl:p-7">
              {isLoading ? (
                <CollectionSkeleton />
              ) : selectedCollection ? (
                <CollectionDetail
                  collection={selectedCollection}
                  documents={collectionDocuments}
                  total={collectionDocumentTotal}
                  isLoading={isLoadingDocuments}
                  isMutating={isMutating}
                  showAddDocuments={showAddDocuments}
                  candidateQuery={candidateQuery}
                  candidateDocuments={
                    candidateDocumentsQuery.data?.documents ?? []
                  }
                  candidateTotal={candidateDocumentsQuery.data?.total ?? 0}
                  isLoadingCandidates={candidateDocumentsQuery.isLoading}
                  candidateError={
                    candidateDocumentsQuery.error instanceof Error
                      ? candidateDocumentsQuery.error.message
                      : null
                  }
                  onCandidateQueryChange={setCandidateQuery}
                  onSearchCandidates={() =>
                    setSubmittedCandidateQuery(candidateQuery.trim())
                  }
                  onToggleAddDocuments={() =>
                    setShowAddDocuments((current) => !current)
                  }
                  onOpenDocument={onOpenDocument}
                  onAddDocument={(documentId) =>
                    onAddDocument(selectedCollection.id, documentId)
                  }
                  onRemoveDocument={(documentId) =>
                    onRemoveDocument(selectedCollection.id, documentId)
                  }
                  onEdit={() => openCollectionEditor(selectedCollection)}
                  onDelete={() =>
                    onDeleteCollection(
                      selectedCollection.id,
                      selectedCollection.name,
                    )
                  }
                  onViewChange={(viewMode) =>
                    onUpdateCollection(selectedCollection.id, {
                      view_mode: viewMode,
                    })
                  }
                />
              ) : collections.length ? (
                <CollectionOverview
                  collections={collections}
                  onSelect={onSelectCollection}
                  onCreate={() => openCollectionEditor()}
                />
              ) : (
                <EmptyCollections onCreate={() => openCollectionEditor()} />
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function SectionTab({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium",
        active
          ? "bg-muted text-foreground"
          : "text-muted-foreground hover:text-foreground",
      )}
      type="button"
      onClick={onClick}
    >
      {label}
      <span className="ml-2 text-xs opacity-70">{count}</span>
    </button>
  );
}

function CollectionOverview({
  collections,
  onSelect,
  onCreate,
}: {
  collections: CollectionItem[];
  onSelect: (collectionId: string) => void;
  onCreate: () => void;
}) {
  return (
    <>
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Your collections</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Manual collections stay curated. Dynamic collections update from
            their rules.
          </p>
        </div>
        <Button variant="ghost" size="sm" type="button" onClick={onCreate}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Create
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {collections.map((collection) => (
          <button
            className="group rounded-lg border border-border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-muted/30"
            key={collection.id}
            type="button"
            onClick={() => onSelect(collection.id)}
          >
            <div className="flex items-start justify-between gap-3">
              <div
                className="flex h-10 w-10 items-center justify-center rounded-lg text-white"
                style={{
                  backgroundColor: collection.color ?? "hsl(var(--primary))",
                }}
              >
                <Folder className="h-5 w-5" aria-hidden="true" />
              </div>
              <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                {collection.kind === "dynamic" ? "Dynamic" : "Manual"}
              </span>
            </div>
            <h3 className="mt-4 truncate font-semibold">{collection.name}</h3>
            <p className="mt-1 line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">
              {collection.description ||
                ruleSummary(collection.rule, collection.kind)}
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              {collection.document_count}{" "}
              {collection.document_count === 1 ? "document" : "documents"}
            </p>
          </button>
        ))}
      </div>
    </>
  );
}

function CollectionDetail({
  collection,
  documents,
  total,
  isLoading,
  isMutating,
  showAddDocuments,
  candidateQuery,
  candidateDocuments,
  candidateTotal,
  isLoadingCandidates,
  candidateError,
  onCandidateQueryChange,
  onSearchCandidates,
  onToggleAddDocuments,
  onOpenDocument,
  onAddDocument,
  onRemoveDocument,
  onEdit,
  onDelete,
  onViewChange,
}: {
  collection: CollectionItem;
  documents: CollectionDocument[];
  total: number;
  isLoading: boolean;
  isMutating: boolean;
  showAddDocuments: boolean;
  candidateQuery: string;
  candidateDocuments: CollectionDocument[];
  candidateTotal: number;
  isLoadingCandidates: boolean;
  candidateError: string | null;
  onCandidateQueryChange: (value: string) => void;
  onSearchCandidates: () => void;
  onToggleAddDocuments: () => void;
  onOpenDocument: (documentId: string) => void;
  onAddDocument: (documentId: string) => void;
  onRemoveDocument: (documentId: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onViewChange: (view: CollectionView) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-white"
            style={{
              backgroundColor: collection.color ?? "hsl(var(--primary))",
            }}
          >
            <Folder className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-xl font-semibold">
                {collection.name}
              </h2>
              <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                {collection.kind === "dynamic" ? "Dynamic" : "Manual"}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {collection.description ||
                ruleSummary(collection.rule, collection.kind)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {collection.kind === "manual" ? (
            <Button
              variant={showAddDocuments ? "secondary" : "outline"}
              size="sm"
              type="button"
              onClick={onToggleAddDocuments}
            >
              {showAddDocuments ? (
                <X className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Plus className="h-4 w-4" aria-hidden="true" />
              )}
              {showAddDocuments ? "Close" : "Add documents"}
            </Button>
          ) : null}
          <Button
            aria-label="Edit collection"
            title="Edit collection"
            variant="ghost"
            size="icon"
            type="button"
            onClick={onEdit}
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            aria-label="Delete collection"
            title="Delete collection"
            variant="ghost"
            size="icon"
            type="button"
            disabled={isMutating}
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
          <span className="mx-1 h-6 w-px bg-border" />
          <Button
            aria-label="Grid view"
            title="Grid view"
            variant={collection.view_mode === "grid" ? "secondary" : "ghost"}
            size="icon"
            type="button"
            onClick={() => onViewChange("grid")}
          >
            <Grid2X2 className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            aria-label="List view"
            title="List view"
            variant={collection.view_mode === "list" ? "secondary" : "ghost"}
            size="icon"
            type="button"
            onClick={() => onViewChange("list")}
          >
            <List className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {collection.kind === "dynamic" ? (
        <div className="flex flex-wrap gap-2 border-b border-border py-4">
          {ruleLabels(collection.rule).map((label) => (
            <span
              className="rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground"
              key={label}
            >
              {label}
            </span>
          ))}
        </div>
      ) : null}

      {showAddDocuments ? (
        <div className="my-5 rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Add documents</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Search the full vault. Existing members are excluded.
              </p>
            </div>
            <span className="text-xs text-muted-foreground">
              {candidateTotal} available
            </span>
          </div>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              onSearchCandidates();
            }}
          >
            <div className="relative min-w-0 flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="Search titles, filenames, issuers, or organizations"
                value={candidateQuery}
                onChange={(event) => onCandidateQueryChange(event.target.value)}
              />
            </div>
            <Button size="sm" type="submit">
              Search
            </Button>
          </form>
          <div className="mt-3 max-h-64 divide-y divide-border overflow-auto rounded-md border border-border">
            {candidateError ? (
              <p className="p-4 text-sm text-rose-700" role="alert">
                {candidateError}
              </p>
            ) : isLoadingCandidates ? (
              <p className="p-4 text-sm text-muted-foreground">Searching...</p>
            ) : candidateDocuments.length ? (
              candidateDocuments.map((document) => (
                <div
                  className="flex items-center gap-3 bg-background px-3 py-2.5"
                  key={document.id}
                >
                  <FileText
                    className="h-4 w-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {document.title}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {humanizeLabel(document.document_type)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    type="button"
                    disabled={isMutating}
                    onClick={() => onAddDocument(document.id)}
                  >
                    Add
                  </Button>
                </div>
              ))
            ) : (
              <p className="p-4 text-sm text-muted-foreground">
                No matching documents are available.
              </p>
            )}
          </div>
        </div>
      ) : null}

      <div className="mb-3 mt-5 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Documents</h3>
        <span className="text-xs text-muted-foreground">{total} total</span>
      </div>
      {isLoading ? (
        <CollectionSkeleton />
      ) : documents.length ? (
        <div
          className={cn(
            collection.view_mode === "grid"
              ? "grid gap-3 sm:grid-cols-2 2xl:grid-cols-3"
              : "divide-y divide-border overflow-hidden rounded-lg border border-border bg-card",
          )}
        >
          {documents.map((document) =>
            collection.view_mode === "grid" ? (
              <CollectionDocumentCard
                key={document.id}
                document={document}
                removable={collection.kind === "manual"}
                onOpen={() => onOpenDocument(document.id)}
                onRemove={() => onRemoveDocument(document.id)}
              />
            ) : (
              <CollectionDocumentRow
                key={document.id}
                document={document}
                removable={collection.kind === "manual"}
                onOpen={() => onOpenDocument(document.id)}
                onRemove={() => onRemoveDocument(document.id)}
              />
            ),
          )}
        </div>
      ) : (
        <div className="flex min-h-72 items-center justify-center rounded-lg border border-dashed border-border bg-card text-center">
          <div className="max-w-sm p-6">
            <Folder className="mx-auto h-8 w-8 text-muted-foreground" />
            <h3 className="mt-3 font-semibold">No documents here</h3>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {collection.kind === "manual"
                ? "Add documents without moving their source files."
                : "No current documents match this collection rule."}
            </p>
          </div>
        </div>
      )}
    </>
  );
}

function CollectionDocumentCard({
  document,
  removable,
  onOpen,
  onRemove,
}: {
  document: CollectionDocument;
  removable: boolean;
  onOpen: () => void;
  onRemove: () => void;
}) {
  return (
    <article className="group rounded-lg border border-border bg-card p-4 shadow-sm">
      <button className="block w-full text-left" type="button" onClick={onOpen}>
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <FileText className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h4 className="truncate text-sm font-semibold">{document.title}</h4>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {document.original_filename}
            </p>
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>{humanizeLabel(document.document_type)}</span>
          <span>{formatDocumentDate(document)}</span>
        </div>
      </button>
      {removable ? (
        <button
          className="mt-3 text-xs text-muted-foreground hover:text-foreground"
          type="button"
          onClick={onRemove}
        >
          Remove from collection
        </button>
      ) : null}
    </article>
  );
}

function CollectionDocumentRow({
  document,
  removable,
  onOpen,
  onRemove,
}: {
  document: CollectionDocument;
  removable: boolean;
  onOpen: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <FileText
        className="h-4 w-4 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
      <button
        className="min-w-0 flex-1 text-left"
        type="button"
        onClick={onOpen}
      >
        <p className="truncate text-sm font-medium">{document.title}</p>
        <p className="truncate text-xs text-muted-foreground">
          {document.original_filename}
        </p>
      </button>
      <span className="hidden text-xs text-muted-foreground sm:block">
        {humanizeLabel(document.document_type)}
      </span>
      <span className="hidden w-24 text-right text-xs text-muted-foreground md:block">
        {formatDocumentDate(document)}
      </span>
      {removable ? (
        <Button
          aria-label={`Remove ${document.title} from collection`}
          title="Remove from collection"
          variant="ghost"
          size="icon"
          type="button"
          onClick={onRemove}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}

function TagsPanel({
  tags,
  isLoading,
  isMutating,
  onEdit,
  onRefresh,
  onDelete,
}: {
  tags: TagItem[];
  isLoading: boolean;
  isMutating: boolean;
  onEdit: (tag: TagItem) => void;
  onRefresh: (tagId: string) => void;
  onDelete: (tagId: string, name: string) => void;
}) {
  if (isLoading)
    return (
      <div className="p-5 xl:p-7">
        <CollectionSkeleton />
      </div>
    );
  if (!tags.length) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6 text-center">
        <div className="max-w-md">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          <h2 className="mt-4 text-lg font-semibold">No tags yet</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Create a manual tag or a smart tag that follows deterministic
            document rules.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="p-5 xl:p-7">
      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {tags.map((tag) => {
          const isSmart = tag.source === "smart";
          return (
            <article
              className="rounded-lg border border-border bg-card p-4 shadow-sm"
              key={tag.id}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <div
                    className="mt-0.5 h-3 w-3 shrink-0 rounded-sm"
                    style={{
                      backgroundColor: tag.color ?? "hsl(var(--primary))",
                    }}
                  />
                  <div className="min-w-0">
                    <h2 className="truncate text-sm font-semibold">
                      {tag.name}
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {tag.document_count}{" "}
                      {tag.document_count === 1 ? "document" : "documents"}
                    </p>
                  </div>
                </div>
                <span
                  className={cn(
                    "rounded-md px-2 py-1 text-xs",
                    isSmart
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {humanizeLabel(tag.source)}
                </span>
              </div>
              <div className="mt-4 flex min-h-14 flex-wrap content-start gap-1.5">
                {isSmart ? (
                  ruleLabels(tag.smart_rule ?? emptyRule).map((label) => (
                    <span
                      className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
                      key={label}
                    >
                      {label}
                    </span>
                  ))
                ) : (
                  <p className="text-sm leading-5 text-muted-foreground">
                    {tag.description ||
                      "Assign this tag from a document or use it in a dynamic collection."}
                  </p>
                )}
              </div>
              <div className="mt-4 flex items-center justify-end gap-1 border-t border-border pt-3">
                {isSmart ? (
                  <>
                    <Button
                      aria-label={`Refresh ${tag.name}`}
                      title="Refresh matches"
                      variant="ghost"
                      size="icon"
                      type="button"
                      disabled={isMutating}
                      onClick={() => onRefresh(tag.id)}
                    >
                      <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button
                      aria-label={`Edit ${tag.name}`}
                      title="Edit smart tag"
                      variant="ghost"
                      size="icon"
                      type="button"
                      onClick={() => onEdit(tag)}
                    >
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </>
                ) : null}
                <Button
                  aria-label={`Delete ${tag.name}`}
                  title="Delete tag"
                  variant="ghost"
                  size="icon"
                  type="button"
                  disabled={isMutating}
                  onClick={() => onDelete(tag.id, tag.name)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function CollectionEditor({
  collection,
  documentTypes,
  tags,
  disabled,
  onCancel,
  onSubmit,
}: {
  collection: CollectionItem | null;
  documentTypes: DocumentTypeDefinition[];
  tags: TagItem[];
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (input: CollectionInput) => void;
}) {
  const [name, setName] = useState(collection?.name ?? "");
  const [description, setDescription] = useState(collection?.description ?? "");
  const [kind, setKind] = useState<CollectionKind>(
    collection?.kind ?? "manual",
  );
  const [viewMode, setViewMode] = useState<CollectionView>(
    collection?.view_mode ?? "grid",
  );
  const [rule, setRule] = useState<DocumentRule>(collection?.rule ?? emptyRule);
  const valid = name.trim() && (kind === "manual" || hasRuleCondition(rule));

  return (
    <EditorFrame
      title={collection ? "Edit collection" : "New collection"}
      description="A collection is a view over documents. Source files remain in the vault."
      onClose={onCancel}
    >
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          onSubmit({
            name: name.trim(),
            description: description.trim() || null,
            kind,
            view_mode: viewMode,
            rule: kind === "dynamic" ? rule : emptyRule,
          });
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Name">
            <input
              className={inputClass}
              value={name}
              autoFocus
              disabled={disabled}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="Default view">
            <select
              className={inputClass}
              value={viewMode}
              disabled={disabled}
              onChange={(event) =>
                setViewMode(event.target.value as CollectionView)
              }
            >
              <option value="grid">Grid</option>
              <option value="list">List</option>
            </select>
          </Field>
        </div>
        <Field label="Description" optional>
          <input
            className={inputClass}
            placeholder="What belongs in this collection?"
            value={description}
            disabled={disabled}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        {!collection ? (
          <div>
            <p className="mb-2 text-sm font-medium">Membership</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <KindOption
                active={kind === "manual"}
                title="Manual"
                detail="Choose each document yourself."
                onClick={() => setKind("manual")}
              />
              <KindOption
                active={kind === "dynamic"}
                title="Dynamic"
                detail="Documents appear when rules match."
                onClick={() => setKind("dynamic")}
              />
            </div>
          </div>
        ) : null}
        {kind === "dynamic" ? (
          <RuleBuilder
            rule={rule}
            documentTypes={documentTypes}
            tags={tags}
            allowTags
            onChange={setRule}
          />
        ) : null}
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" type="button" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={disabled || !valid}>
            {collection ? "Save changes" : "Create collection"}
          </Button>
        </div>
      </form>
    </EditorFrame>
  );
}

function TagEditor({
  disabled,
  onCancel,
  onSubmit,
}: {
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (input: {
    name: string;
    description?: string | null;
    color?: string | null;
  }) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  return (
    <EditorFrame
      title="New tag"
      description="Manual tags stay under your control and can be reused in search and collection rules."
      onClose={onCancel}
    >
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          onSubmit({
            name: name.trim(),
            description: description.trim() || null,
          });
        }}
      >
        <Field label="Name">
          <input
            className={inputClass}
            autoFocus
            value={name}
            disabled={disabled}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Description" optional>
          <input
            className={inputClass}
            value={description}
            disabled={disabled}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" type="button" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={disabled || !name.trim()}>
            Create tag
          </Button>
        </div>
      </form>
    </EditorFrame>
  );
}

function SmartTagEditor({
  tag,
  documentTypes,
  disabled,
  onCancel,
  onSubmit,
}: {
  tag: TagItem | null;
  documentTypes: DocumentTypeDefinition[];
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (input: {
    name: string;
    description?: string | null;
    color?: string | null;
    rule: DocumentRule;
  }) => void;
}) {
  const [name, setName] = useState(tag?.name ?? "");
  const [description, setDescription] = useState(tag?.description ?? "");
  const [rule, setRule] = useState<DocumentRule>(tag?.smart_rule ?? emptyRule);
  const valid = name.trim() && hasRuleCondition(rule);

  return (
    <EditorFrame
      title={tag ? "Edit smart tag" : "New smart tag"}
      description="Smart tags use deterministic document fields and never depend on model similarity."
      onClose={onCancel}
    >
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          onSubmit({
            name: name.trim(),
            description: description.trim() || null,
            rule: { ...rule, tags_any: [], include_archived: false },
          });
        }}
      >
        <Field label="Name">
          <input
            className={inputClass}
            value={name}
            autoFocus
            disabled={disabled || tag !== null}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        {!tag ? (
          <Field label="Description" optional>
            <input
              className={inputClass}
              value={description}
              disabled={disabled}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
        ) : null}
        <RuleBuilder
          rule={rule}
          documentTypes={documentTypes}
          tags={[]}
          allowTags={false}
          onChange={setRule}
        />
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" type="button" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={disabled || !valid}>
            {tag ? "Save rule" : "Create smart tag"}
          </Button>
        </div>
      </form>
    </EditorFrame>
  );
}

function RuleBuilder({
  rule,
  documentTypes,
  tags,
  allowTags,
  onChange,
}: {
  rule: DocumentRule;
  documentTypes: DocumentTypeDefinition[];
  tags: TagItem[];
  allowTags: boolean;
  onChange: (rule: DocumentRule) => void;
}) {
  return (
    <div>
      <div className="mb-3">
        <p className="text-sm font-medium">Matching rules</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Every populated field must match. Multiple types or tags match any
          selected value.
        </p>
      </div>
      <div className="grid gap-4 rounded-lg border border-border bg-muted/20 p-4 md:grid-cols-2">
        <Field label="Document type" optional>
          <select
            className={inputClass}
            value={rule.document_types[0] ?? ""}
            onChange={(event) =>
              onChange({
                ...rule,
                document_types: event.target.value ? [event.target.value] : [],
              })
            }
          >
            <option value="">Any type</option>
            {documentTypes.map((definition) => (
              <option key={definition.key} value={definition.key}>
                {definition.label}
              </option>
            ))}
          </select>
        </Field>
        {allowTags ? (
          <Field label="Has tag" optional>
            <select
              className={inputClass}
              value={rule.tags_any[0] ?? ""}
              onChange={(event) =>
                onChange({
                  ...rule,
                  tags_any: event.target.value ? [event.target.value] : [],
                })
              }
            >
              <option value="">Any tag</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.slug}>
                  {tag.name}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <Field label="Title contains" optional>
            <input
              className={inputClass}
              value={rule.title_contains ?? ""}
              onChange={(event) =>
                onChange({
                  ...rule,
                  title_contains: event.target.value || null,
                })
              }
            />
          </Field>
        )}
        {allowTags ? (
          <Field label="Title contains" optional>
            <input
              className={inputClass}
              value={rule.title_contains ?? ""}
              onChange={(event) =>
                onChange({
                  ...rule,
                  title_contains: event.target.value || null,
                })
              }
            />
          </Field>
        ) : null}
        <Field label="Issuer contains" optional>
          <input
            className={inputClass}
            value={rule.issuer_contains ?? ""}
            onChange={(event) =>
              onChange({
                ...rule,
                issuer_contains: event.target.value || null,
              })
            }
          />
        </Field>
        <Field label="Organization contains" optional>
          <input
            className={inputClass}
            value={rule.organization_contains ?? ""}
            onChange={(event) =>
              onChange({
                ...rule,
                organization_contains: event.target.value || null,
              })
            }
          />
        </Field>
        <Field label="Date from" optional>
          <input
            className={inputClass}
            type="date"
            value={rule.date_from ?? ""}
            onChange={(event) =>
              onChange({
                ...rule,
                date_from: event.target.value || null,
              })
            }
          />
        </Field>
        <Field label="Date to" optional>
          <input
            className={inputClass}
            type="date"
            value={rule.date_to ?? ""}
            onChange={(event) =>
              onChange({
                ...rule,
                date_to: event.target.value || null,
              })
            }
          />
        </Field>
        {allowTags ? (
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              checked={rule.include_archived}
              onChange={(event) =>
                onChange({ ...rule, include_archived: event.target.checked })
              }
            />
            Include archived documents
          </label>
        ) : null}
      </div>
    </div>
  );
}

function EditorFrame({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl p-5 xl:p-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        <Button
          aria-label="Close editor"
          title="Close"
          variant="ghost"
          size="icon"
          type="button"
          onClick={onClose}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">
        {label}
        {optional ? (
          <span className="ml-1 font-normal text-muted-foreground">
            optional
          </span>
        ) : null}
      </span>
      {children}
    </label>
  );
}

function KindOption({
  active,
  title,
  detail,
  onClick,
}: {
  active: boolean;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "rounded-lg border p-3 text-left",
        active
          ? "border-primary bg-primary/5"
          : "border-border hover:bg-muted/40",
      )}
      type="button"
      onClick={onClick}
    >
      <span className="text-sm font-medium">{title}</span>
      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
        {detail}
      </span>
    </button>
  );
}

function EmptyCollections({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center text-center">
      <div className="max-w-md">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <FolderKanban className="h-5 w-5" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">
          Create your first collection
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Group documents manually or define a rule that keeps the collection
          current automatically.
        </p>
        <Button className="mt-5" type="button" onClick={onCreate}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          New collection
        </Button>
      </div>
    </div>
  );
}

function CollectionSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          className="h-32 animate-pulse rounded-lg border border-border bg-card"
          key={index}
        />
      ))}
    </div>
  );
}

function hasRuleCondition(rule: DocumentRule) {
  return Boolean(
    rule.document_types.length ||
    rule.title_contains?.trim() ||
    rule.issuer_contains?.trim() ||
    rule.organization_contains?.trim() ||
    rule.date_from ||
    rule.date_to ||
    rule.tags_any.length,
  );
}

function ruleLabels(rule: DocumentRule) {
  const labels: string[] = [];
  if (rule.document_types.length) {
    labels.push(`Type: ${rule.document_types.map(humanizeLabel).join(", ")}`);
  }
  if (rule.title_contains)
    labels.push(`Title contains "${rule.title_contains}"`);
  if (rule.issuer_contains)
    labels.push(`Issuer contains "${rule.issuer_contains}"`);
  if (rule.organization_contains)
    labels.push(`Organization contains "${rule.organization_contains}"`);
  if (rule.date_from) labels.push(`From ${formatDate(rule.date_from)}`);
  if (rule.date_to) labels.push(`Until ${formatDate(rule.date_to)}`);
  if (rule.tags_any.length)
    labels.push(`Tag: ${rule.tags_any.map(humanizeLabel).join(", ")}`);
  if (rule.include_archived) labels.push("Includes archived");
  return labels.length ? labels : ["No matching conditions"];
}

function ruleSummary(rule: DocumentRule, kind: CollectionKind) {
  if (kind === "manual") return "Curated document collection";
  return ruleLabels(rule).join(" | ");
}

function formatDocumentDate(document: CollectionDocument) {
  return formatDate(document.document_date ?? document.created_at);
}

function formatDate(value: string) {
  const normalizedValue = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value}T00:00:00`
    : value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(normalizedValue));
}

const inputClass =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";
