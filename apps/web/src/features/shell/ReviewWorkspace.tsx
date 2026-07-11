import { AlertTriangle, CheckCircle2, FileCheck2 } from "lucide-react";

import { Button } from "../../components/ui/button";
import { DocumentItem, DocumentTypeDefinition } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";
import { formatReviewReason } from "./review-utils";

export function ReviewWorkspace({
  documents,
  documentTypes,
  isLoading,
  isUpdating,
  onOpenDocument,
  onApprove,
}: {
  documents: DocumentItem[];
  documentTypes: DocumentTypeDefinition[];
  isLoading: boolean;
  isUpdating: boolean;
  onOpenDocument: (documentId: string) => void;
  onApprove: (documentId: string) => void;
}) {
  const typeLabels = new Map(
    documentTypes.map((definition) => [definition.key, definition.label]),
  );

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-8">
        <p className="text-xs font-medium uppercase text-muted-foreground">
          Quality control
        </p>
        <h1 className="mt-1 text-2xl font-semibold">Review</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Confirm low-confidence classifications and incomplete metadata.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-8">
        <div className="mx-auto max-w-6xl">
          {isLoading ? (
            <div className="h-48 animate-pulse rounded-lg border border-border bg-muted" />
          ) : documents.length ? (
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="hidden grid-cols-[minmax(0,1fr)_180px_minmax(220px,1fr)_190px] gap-4 border-b border-border bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground lg:grid">
                <span>Document</span>
                <span>Type</span>
                <span>Review reason</span>
                <span className="text-right">Actions</span>
              </div>
              <div className="divide-y divide-border">
                {documents.map((document) => (
                  <div
                    className="grid gap-3 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_180px_minmax(220px,1fr)_190px] lg:items-center"
                    key={document.id}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                        <AlertTriangle className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {document.title}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {document.original_filename}
                        </p>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {typeLabels.get(document.document_type) ??
                        humanizeLabel(document.document_type)}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {document.review_reasons.slice(0, 3).map((reason) => (
                        <span
                          className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
                          key={reason}
                        >
                          {formatReviewReason(reason)}
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2 lg:justify-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onOpenDocument(document.id)}
                      >
                        Review
                      </Button>
                      <Button
                        size="sm"
                        disabled={isUpdating}
                        onClick={() => onApprove(document.id)}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        Approve
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border bg-card px-6 py-16 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                <FileCheck2 className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-base font-semibold">
                Review queue is clear
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Documents needing attention will appear here.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
