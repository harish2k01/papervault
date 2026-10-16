import { ArrowUpRight, FileText } from "lucide-react";

import type { DocumentItem } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";

export type LibraryDocument = Pick<
  DocumentItem,
  | "id"
  | "title"
  | "original_filename"
  | "document_type"
  | "status"
  | "created_at"
> & { highlights?: string[] };

function documentPalette(type: string) {
  if (/insurance|identity|passport|medical/.test(type)) return "orchid";
  if (/salary|tax|bank|statement|employment/.test(type)) return "mint";
  if (/receipt|warranty|property/.test(type)) return "amber";
  return "cobalt";
}

export function DocumentCard({
  document,
  typeLabel,
  onOpen,
}: {
  document: LibraryDocument;
  typeLabel?: string;
  onOpen: (documentId: string) => void;
}) {
  const label = typeLabel ?? humanizeLabel(document.document_type);
  const highlight = document.highlights?.[0]?.replace(/<\/?em>/g, "");

  return (
    <button
      className="pv-document-card group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      type="button"
      onClick={() => onOpen(document.id)}
    >
      <span
        className="pv-document-cover"
        data-palette={documentPalette(document.document_type)}
      >
        <span className="flex items-center justify-between gap-3">
          <FileText className="h-5 w-5" aria-hidden="true" />
          <ArrowUpRight
            className="h-4 w-4 opacity-60 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
        <span className="mt-7 block text-xs font-medium uppercase tracking-wider">
          {label}
        </span>
        <span className="mt-1 block break-words text-xs opacity-80">
          {document.original_filename}
        </span>
      </span>
      <span className="flex flex-1 flex-col p-4">
        <span className="break-words text-sm font-medium">
          {document.title}
        </span>
        {highlight ? (
          <span className="mt-2 line-clamp-3 break-words text-xs leading-5 text-muted-foreground">
            {highlight}
          </span>
        ) : null}
        <span className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4 text-xs text-muted-foreground">
          <span className="pv-document-status" data-status={document.status}>
            {document.status === "ready"
              ? "Text available"
              : humanizeLabel(document.status)}
          </span>
          <time dateTime={document.created_at}>
            {new Date(document.created_at).toLocaleDateString(undefined, {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </time>
        </span>
      </span>
    </button>
  );
}
