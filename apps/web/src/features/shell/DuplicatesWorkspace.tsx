import { useMemo, useState } from "react";
import {
  Archive,
  CheckCircle2,
  FileSearch,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import {
  DuplicateGroup,
  DuplicateMethod,
  DuplicateRefreshResult,
} from "../../lib/api";
import { cn, humanizeLabel } from "../../lib/utils";

type MergeInput = {
  keep_document_id: string;
  duplicate_document_ids: string[];
  match_method: DuplicateMethod;
  confirm_non_exact: boolean;
};

export function DuplicatesWorkspace({
  groups,
  isLoading,
  isResolving,
  isScanning,
  scanResult,
  error,
  onOpenDocument,
  onMerge,
  onScan,
}: {
  groups: DuplicateGroup[];
  isLoading: boolean;
  isResolving: boolean;
  isScanning: boolean;
  scanResult: DuplicateRefreshResult | undefined;
  error: string | null;
  onOpenDocument: (documentId: string) => void;
  onMerge: (input: MergeInput) => void;
  onScan: () => void;
}) {
  const [keepers, setKeepers] = useState<Record<string, string>>({});
  const [confirmations, setConfirmations] = useState<Record<string, boolean>>(
    {},
  );
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
        }))
        .sort(
          (left, right) =>
            methodPriority(left.method) - methodPriority(right.method) ||
            right.confidence - left.confidence,
        ),
    [groups],
  );
  const duplicateCount = sortedGroups.reduce(
    (total, group) => total + Math.max(group.documents.length - 1, 0),
    0,
  );
  const exactGroups = sortedGroups.filter(
    (group) =>
      group.method === "sha256_hash" || group.method === "normalized_text",
  ).length;
  const similarityGroups = sortedGroups.length - exactGroups;

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-4 xl:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Duplicate review</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Compare likely copies and archive only the records you confirm.
            </p>
          </div>
          <div className="text-right">
            <Button
              type="button"
              variant="outline"
              disabled={isScanning}
              onClick={onScan}
            >
              <RefreshCw
                className={cn("h-4 w-4", isScanning && "animate-spin")}
                aria-hidden="true"
              />
              {isScanning ? "Scanning" : "Scan library"}
            </Button>
            {scanResult ? (
              <p className="mt-1.5 text-xs text-muted-foreground">
                {scanResult.updated > 0
                  ? `${scanResult.updated} fingerprints updated`
                  : "Fingerprints are up to date"}
              </p>
            ) : null}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-border pt-3 text-sm">
          <Metric label="Groups" value={sortedGroups.length} />
          <Metric label="Redundant copies" value={duplicateCount} />
          <Metric label="Exact" value={exactGroups} />
          <Metric label="Similar" value={similarityGroups} />
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-5 xl:px-8">
        {error ? (
          <p
            className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                className="h-52 animate-pulse rounded-lg border border-border bg-card"
                key={index}
              />
            ))}
          </div>
        ) : sortedGroups.length === 0 ? (
          <EmptyDuplicates isScanning={isScanning} onScan={onScan} />
        ) : (
          <div className="space-y-4">
            {sortedGroups.map((group) => {
              const groupKey = duplicateGroupKey(group);
              const keepDocumentId = keepers[groupKey] ?? group.documents[0].id;
              const duplicateDocumentIds = group.documents
                .filter((document) => document.id !== keepDocumentId)
                .map((document) => document.id);
              const confirmed = confirmations[groupKey] === true;
              const canResolve =
                duplicateDocumentIds.length > 0 &&
                (!group.requires_confirmation || confirmed);

              return (
                <article
                  className="overflow-hidden rounded-lg border border-border bg-card"
                  key={groupKey}
                >
                  <div className="flex flex-col gap-4 border-b border-border px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={methodBadgeClass(group.method)}>
                          {methodLabel(group.method)}
                        </span>
                        <span className="text-xs font-medium text-muted-foreground">
                          {formatPercent(group.confidence)} confidence
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6">
                        {group.explanation}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span>
                          Text {formatPercent(group.signals.text_similarity)}
                        </span>
                        <span>
                          Length{" "}
                          {formatPercent(group.signals.length_similarity)}
                        </span>
                        {group.signals.shared_bands > 0 ? (
                          <span>
                            {group.signals.shared_bands} matching bands
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <Button
                      type="button"
                      disabled={isResolving || !canResolve}
                      onClick={() =>
                        onMerge({
                          keep_document_id: keepDocumentId,
                          duplicate_document_ids: duplicateDocumentIds,
                          match_method: group.method,
                          confirm_non_exact: confirmed,
                        })
                      }
                    >
                      <Archive className="h-4 w-4" aria-hidden="true" />
                      Archive {duplicateDocumentIds.length} duplicate
                      {duplicateDocumentIds.length === 1 ? "" : "s"}
                    </Button>
                  </div>

                  <div className="grid divide-y divide-border lg:grid-cols-2 lg:divide-x lg:divide-y-0">
                    {group.documents.map((document) => {
                      const selected = document.id === keepDocumentId;
                      return (
                        <div
                          className={cn(
                            "p-4 transition-colors",
                            selected && "bg-primary/[0.035]",
                          )}
                          key={document.id}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h2 className="truncate text-sm font-semibold">
                                {document.title}
                              </h2>
                              <p className="mt-1 truncate text-xs text-muted-foreground">
                                {document.original_filename}
                              </p>
                            </div>
                            {selected ? (
                              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                                <CheckCircle2
                                  className="h-3 w-3"
                                  aria-hidden="true"
                                />
                                Keep
                              </span>
                            ) : null}
                          </div>
                          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                            <DocumentFact
                              label="Type"
                              value={humanizeLabel(document.document_type)}
                            />
                            <DocumentFact
                              label="Added"
                              value={formatDate(document.created_at)}
                            />
                            <DocumentFact
                              label="Size"
                              value={formatFileSize(document.file_size_bytes)}
                            />
                            <DocumentFact
                              label="Pages"
                              value={
                                document.page_count?.toString() ?? "Unknown"
                              }
                            />
                          </dl>
                          <div className="mt-4 flex gap-2">
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

                  {group.requires_confirmation ? (
                    <label className="flex cursor-pointer items-start gap-3 border-t border-border bg-muted/25 px-4 py-3 text-sm">
                      <input
                        className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
                        type="checkbox"
                        checked={confirmed}
                        onChange={(event) =>
                          setConfirmations((current) => ({
                            ...current,
                            [groupKey]: event.target.checked,
                          }))
                        }
                      />
                      <span>
                        I reviewed these documents and confirm they represent
                        the same source record.
                      </span>
                    </label>
                  ) : (
                    <div className="flex items-center gap-2 border-t border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
                      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                      Cryptographic file hashes match; manual confirmation is
                      not required.
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function EmptyDuplicates({
  isScanning,
  onScan,
}: {
  isScanning: boolean;
  onScan: () => void;
}) {
  return (
    <div className="flex min-h-[440px] items-center justify-center text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          {isScanning ? (
            <RefreshCw className="h-5 w-5 animate-spin" aria-hidden="true" />
          ) : (
            <FileSearch className="h-5 w-5" aria-hidden="true" />
          )}
        </div>
        <h2 className="mt-4 text-lg font-semibold">No duplicate candidates</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          New documents are fingerprinted during processing. Scan once to
          evaluate documents added before similarity detection was enabled.
        </p>
        <Button
          className="mt-5"
          type="button"
          variant="outline"
          disabled={isScanning}
          onClick={onScan}
        >
          <ScanSearch className="h-4 w-4" aria-hidden="true" />
          {isScanning ? "Scanning library" : "Scan library"}
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <span>
      <strong className="font-semibold text-foreground">{value}</strong>{" "}
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}

function DocumentFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-foreground">{value}</dd>
    </div>
  );
}

function duplicateGroupKey(group: DuplicateGroup) {
  const ids = group.documents.map((document) => document.id).sort();
  return `${group.method}:${ids.join(":")}`;
}

function methodPriority(method: DuplicateMethod) {
  return {
    sha256_hash: 0,
    normalized_text: 1,
    content_similarity: 2,
    ocr_similarity: 3,
  }[method];
}

function methodLabel(method: DuplicateMethod) {
  return {
    sha256_hash: "Exact file",
    normalized_text: "Exact text",
    content_similarity: "Similar content",
    ocr_similarity: "OCR similarity",
  }[method];
}

function methodBadgeClass(method: DuplicateMethod) {
  return cn(
    "rounded-full px-2 py-1 text-xs font-medium",
    method === "sha256_hash"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : method === "normalized_text"
        ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
        : "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  );
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
