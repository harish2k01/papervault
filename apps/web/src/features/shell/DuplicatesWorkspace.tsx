import { useMemo, useState } from "react";
import {
  Archive,
  CheckCircle2,
  Copy,
  FileSearch,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import { DuplicateGroup } from "../../lib/api";
import { cn } from "../../lib/utils";

export function DuplicatesWorkspace({
  groups,
  isLoading,
  isResolving,
  error,
  onOpenDocument,
  onMerge,
}: {
  groups: DuplicateGroup[];
  isLoading: boolean;
  isResolving: boolean;
  error: string | null;
  onOpenDocument: (documentId: string) => void;
  onMerge: (input: {
    keep_document_id: string;
    duplicate_document_ids: string[];
  }) => void;
}) {
  const [keepers, setKeepers] = useState<Record<string, string>>({});
  const sortedGroups = useMemo(
    () =>
      groups
        .filter((group) => group.documents.length > 1)
        .map((group) => ({
          ...group,
          documents: [...group.documents].sort(
            (left, right) =>
              new Date(left.created_at).getTime() -
              new Date(right.created_at).getTime(),
          ),
        })),
    [groups],
  );
  const duplicateCount = sortedGroups.reduce(
    (total, group) => total + Math.max(group.documents.length - 1, 0),
    0,
  );

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Duplicate resolution
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal">
              Duplicates
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              Review exact file matches, choose the document to keep, and
              archive redundant copies without deleting source objects.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
            <span className="font-semibold">{duplicateCount}</span>
            <span className="ml-1 text-muted-foreground">duplicates</span>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-7">
        <div className="grid gap-3 md:grid-cols-3">
          <DuplicateStatCard
            icon={Copy}
            label="Groups"
            value={sortedGroups.length}
          />
          <DuplicateStatCard
            icon={Archive}
            label="Can archive"
            value={duplicateCount}
          />
          <DuplicateStatCard
            icon={ShieldCheck}
            label="Method"
            value="Exact hash"
          />
        </div>

        {error ? (
          <p
            className="mt-5 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {isLoading ? (
          <div className="mt-6 space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                className="h-44 animate-pulse rounded-xl border border-border bg-card"
                key={index}
              />
            ))}
          </div>
        ) : sortedGroups.length === 0 ? (
          <div className="mt-6 flex min-h-[420px] items-center justify-center rounded-xl border border-dashed border-border bg-card p-8 text-center">
            <div className="max-w-sm">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <FileSearch className="h-5 w-5" aria-hidden="true" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">
                No exact duplicates
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                PaperVault will list exact SHA-256 matches here after upload and
                processing.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {sortedGroups.map((group) => {
              const groupKey = duplicateGroupKey(group);
              const keepDocumentId = keepers[groupKey] ?? group.documents[0].id;
              const duplicateDocumentIds = group.documents
                .filter((document) => document.id !== keepDocumentId)
                .map((document) => document.id);

              return (
                <article
                  className="rounded-xl border border-border bg-card shadow-sm"
                  key={groupKey}
                >
                  <div className="flex flex-col gap-4 border-b border-border p-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-sm font-semibold">
                        {group.documents.length} matching files
                      </h2>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {group.method.replaceAll("_", " ")} -{" "}
                        {group.documents[0].sha256_hash.slice(0, 16)}
                      </p>
                    </div>
                    <Button
                      type="button"
                      disabled={
                        isResolving || duplicateDocumentIds.length === 0
                      }
                      onClick={() =>
                        onMerge({
                          keep_document_id: keepDocumentId,
                          duplicate_document_ids: duplicateDocumentIds,
                        })
                      }
                    >
                      Archive {duplicateDocumentIds.length} duplicate
                      {duplicateDocumentIds.length === 1 ? "" : "s"}
                    </Button>
                  </div>

                  <div className="grid gap-3 p-4 lg:grid-cols-2">
                    {group.documents.map((document) => {
                      const selected = document.id === keepDocumentId;
                      return (
                        <div
                          className={cn(
                            "rounded-lg border p-3 transition-colors",
                            selected
                              ? "border-primary bg-primary/5"
                              : "border-border bg-background",
                          )}
                          key={document.id}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="truncate text-sm font-semibold">
                                {document.title}
                              </h3>
                              <p className="mt-1 truncate text-xs text-muted-foreground">
                                {document.original_filename}
                              </p>
                            </div>
                            {selected ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-xs text-primary">
                                <CheckCircle2
                                  className="h-3 w-3"
                                  aria-hidden="true"
                                />
                                Keep
                              </span>
                            ) : null}
                          </div>

                          <p className="mt-3 text-xs text-muted-foreground">
                            Added {formatDate(document.created_at)}
                          </p>

                          <div className="mt-3 flex flex-wrap gap-2">
                            <Button
                              size="sm"
                              variant={selected ? "secondary" : "outline"}
                              type="button"
                              disabled={isResolving}
                              onClick={() =>
                                setKeepers((current) => ({
                                  ...current,
                                  [groupKey]: document.id,
                                }))
                              }
                            >
                              Keep this
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              type="button"
                              onClick={() => onOpenDocument(document.id)}
                            >
                              Open
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function DuplicateStatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function duplicateGroupKey(group: DuplicateGroup) {
  return `${group.method}:${group.documents[0]?.sha256_hash ?? "empty"}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
