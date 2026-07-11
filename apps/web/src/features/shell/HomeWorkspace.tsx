import {
  ArrowRight,
  BellRing,
  Clock3,
  FileText,
  MessageSquareText,
  Upload,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import { DocumentItem, NotificationItem } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";

export function HomeWorkspace({
  documents,
  notifications,
  isLoading,
  isUploading,
  onUpload,
  onOpenDocument,
  onOpenDocuments,
  onAsk,
}: {
  documents: DocumentItem[];
  notifications: NotificationItem[];
  isLoading: boolean;
  isUploading: boolean;
  onUpload: (file: File) => void;
  onOpenDocument: (documentId: string) => void;
  onOpenDocuments: () => void;
  onAsk: () => void;
}) {
  const ready = documents.filter(
    (document) => document.status === "ready",
  ).length;
  const processing = documents.filter((document) =>
    document.status.includes("processing"),
  ).length;
  const due = notifications.filter(
    (notification) => notification.status === "pending",
  ).length;
  const recent = documents.slice(0, 6);

  return (
    <section className="min-w-0 flex-1 overflow-auto bg-background">
      <header className="border-b border-border bg-card px-5 py-5 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Personal knowledge base
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Your vault</h1>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onAsk}>
              <MessageSquareText className="h-4 w-4" />
              Ask
            </Button>
            <UploadButton disabled={isUploading} onUpload={onUpload} />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-8 p-5 lg:p-8">
        <div className="grid divide-y rounded-lg border border-border bg-card sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <VaultMetric icon={FileText} label="Ready documents" value={ready} />
          <VaultMetric icon={Clock3} label="Processing" value={processing} />
          <VaultMetric icon={BellRing} label="Due soon" value={due} />
        </div>

        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Recent documents</h2>
              <p className="text-sm text-muted-foreground">
                Continue reviewing your latest uploads.
              </p>
            </div>
            {documents.length ? (
              <Button variant="ghost" size="sm" onClick={onOpenDocuments}>
                View all
                <ArrowRight className="h-4 w-4" />
              </Button>
            ) : null}
          </div>

          {isLoading ? (
            <div className="h-48 animate-pulse rounded-lg border border-border bg-muted" />
          ) : recent.length ? (
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="divide-y divide-border">
                {recent.map((document) => (
                  <button
                    className="grid w-full gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/60 sm:grid-cols-[minmax(0,1fr)_180px_120px] sm:items-center"
                    key={document.id}
                    type="button"
                    onClick={() => onOpenDocument(document.id)}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {document.title}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {document.original_filename}
                      </span>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {humanizeLabel(document.document_type)}
                    </span>
                    <span className="text-xs text-muted-foreground sm:text-right">
                      {new Date(document.created_at).toLocaleDateString()}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border bg-card px-6 py-14 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Upload className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-base font-semibold">
                Add your first document
              </h2>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Upload a PDF, scan, or image to extract, classify, and search
                it.
              </p>
              <div className="mt-5 flex justify-center">
                <UploadButton disabled={isUploading} onUpload={onUpload} />
              </div>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function VaultMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-4">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function UploadButton({
  disabled,
  onUpload,
}: {
  disabled: boolean;
  onUpload: (file: File) => void;
}) {
  return (
    <Button asChild disabled={disabled}>
      <label className="cursor-pointer">
        <Upload className="h-4 w-4" />
        Upload
        <input
          className="sr-only"
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          disabled={disabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
        />
      </label>
    </Button>
  );
}
