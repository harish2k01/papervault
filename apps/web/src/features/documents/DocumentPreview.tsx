import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { Button } from "../../components/ui/button";
import {
  DocumentItem,
  DocumentTextSearchResult,
  OcrTextBlock,
  getDocumentFile,
  getOcrTextBlocks,
  searchDocumentText,
} from "../../lib/api";
import { cn } from "../../lib/utils";
import { renderHighlightedText } from "./document-preview-utils";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MIN_QUERY_LENGTH = 2;

export function DocumentPreview({
  document,
  ocrGeometryAvailable = false,
}: {
  document: DocumentItem;
  ocrGeometryAvailable?: boolean;
}) {
  const canLoadPreview = document.status === "ready";
  const fileQuery = useQuery({
    queryKey: ["document-file", document.id],
    queryFn: () => getDocumentFile(document.id),
    enabled: canLoadPreview,
    staleTime: 5 * 60 * 1000,
  });
  const [queryInput, setQueryInput] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [activeMatchIndex, setActiveMatchIndex] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(
    document.content_type.startsWith("image/") ? 1 : 0,
  );
  const [zoom, setZoom] = useState(1);
  const viewerRef = useRef<HTMLDivElement>(null);
  const [viewerWidth, setViewerWidth] = useState(760);

  const searchQuery = useQuery({
    queryKey: ["document-text-search", document.id, submittedQuery],
    queryFn: () => searchDocumentText(document.id, submittedQuery),
    enabled: submittedQuery.length >= MIN_QUERY_LENGTH,
  });
  const ocrBlocksQuery = useQuery({
    queryKey: ["ocr-blocks", document.id, pageNumber, submittedQuery],
    queryFn: () => getOcrTextBlocks(document.id, pageNumber, submittedQuery),
    enabled: ocrGeometryAvailable && submittedQuery.length >= MIN_QUERY_LENGTH,
  });
  const matches = searchQuery.data?.matches ?? [];

  const imageUrl = useMemo(
    () =>
      document.content_type.startsWith("image/") && fileQuery.data
        ? URL.createObjectURL(fileQuery.data)
        : null,
    [document.content_type, fileQuery.data],
  );

  useEffect(() => {
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, [imageUrl]);

  useEffect(() => {
    if (!viewerRef.current || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      setViewerWidth(Math.max(280, Math.floor(entry.contentRect.width - 32)));
    });
    observer.observe(viewerRef.current);
    return () => observer.disconnect();
  }, [fileQuery.data]);

  useEffect(() => {
    setActiveMatchIndex(0);
    const firstPage = searchQuery.data?.matches[0]?.page_number;
    if (firstPage) {
      setPageNumber(firstPage);
    }
  }, [searchQuery.data]);

  const textRenderer = useMemo(
    () =>
      submittedQuery
        ? ({ str }: { str: string }) =>
            renderHighlightedText(str, submittedQuery)
        : undefined,
    [submittedQuery],
  );

  if (!canLoadPreview) {
    return <PreviewUnavailable />;
  }
  if (fileQuery.isLoading) {
    return <PreviewMessage message="Loading preview..." />;
  }
  if (!fileQuery.data || fileQuery.isError) {
    return <PreviewMessage message="Preview unavailable." />;
  }

  const activateMatch = (index: number) => {
    const match = matches[index];
    setActiveMatchIndex(index);
    if (match?.page_number) {
      setPageNumber(match.page_number);
    }
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const normalized = queryInput.trim();
    setSubmittedQuery(normalized.length >= MIN_QUERY_LENGTH ? normalized : "");
  };

  const isImage = document.content_type.startsWith("image/");
  const hasSearch = submittedQuery.length >= MIN_QUERY_LENGTH;
  const renderedPageWidth = Math.min(viewerWidth, 920) * zoom;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-card px-3 py-2">
        <form
          className="flex w-full min-w-0 items-center gap-2 sm:w-auto sm:min-w-[320px] sm:flex-1"
          onSubmit={submitSearch}
        >
          <div className="relative min-w-[190px] max-w-md flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              aria-label="Search this document"
              className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Search inside document"
              type="search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
            />
          </div>
          <Button
            size="sm"
            type="submit"
            disabled={queryInput.trim().length < MIN_QUERY_LENGTH}
          >
            Search
          </Button>
        </form>

        {!isImage ? (
          <div
            className="flex w-full items-center justify-end gap-1 border-t border-border pt-2 sm:w-auto sm:border-t-0 sm:pt-0"
            aria-label="Document page controls"
          >
            <ViewerIconButton
              label="Previous page"
              disabled={pageNumber <= 1}
              onClick={() =>
                setPageNumber((current) => Math.max(1, current - 1))
              }
            >
              <ChevronLeft className="h-4 w-4" />
            </ViewerIconButton>
            <span className="min-w-16 text-center text-xs tabular-nums text-muted-foreground">
              {pageNumber} / {pageCount || "-"}
            </span>
            <ViewerIconButton
              label="Next page"
              disabled={pageCount === 0 || pageNumber >= pageCount}
              onClick={() =>
                setPageNumber((current) => Math.min(pageCount, current + 1))
              }
            >
              <ChevronRight className="h-4 w-4" />
            </ViewerIconButton>
            <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
            <ViewerIconButton
              label="Zoom out"
              disabled={zoom <= 0.75}
              onClick={() =>
                setZoom((current) => Math.max(0.75, current - 0.25))
              }
            >
              <ZoomOut className="h-4 w-4" />
            </ViewerIconButton>
            <ViewerIconButton
              label="Zoom in"
              disabled={zoom >= 1.75}
              onClick={() =>
                setZoom((current) => Math.min(1.75, current + 0.25))
              }
            >
              <ZoomIn className="h-4 w-4" />
            </ViewerIconButton>
          </div>
        ) : null}
      </div>

      <div
        className={cn(
          "grid min-w-0",
          hasSearch && "lg:grid-cols-[minmax(0,1fr)_300px]",
        )}
      >
        <div
          className="flex min-h-[420px] min-w-0 items-start justify-center overflow-auto bg-muted/60 p-4"
          ref={viewerRef}
        >
          {isImage ? (
            <div className="relative inline-block max-w-full">
              <img
                alt={document.title}
                className="block max-h-[680px] max-w-full rounded-sm bg-white object-contain shadow-sm"
                src={imageUrl ?? undefined}
              />
              <OcrHighlightOverlay blocks={ocrBlocksQuery.data ?? []} />
            </div>
          ) : (
            <Document
              file={fileQuery.data}
              loading={<PreviewMessage message="Rendering document..." />}
              error={
                <PreviewMessage message="This PDF could not be rendered." />
              }
              onLoadSuccess={({ numPages }) => {
                setPageCount(numPages);
                setPageNumber((current) =>
                  Math.min(Math.max(current, 1), numPages),
                );
              }}
            >
              <div className="relative inline-block">
                <Page
                  className="overflow-hidden rounded-sm bg-white shadow-sm"
                  customTextRenderer={textRenderer}
                  pageNumber={pageNumber}
                  renderAnnotationLayer
                  renderTextLayer
                  width={renderedPageWidth}
                />
                <OcrHighlightOverlay blocks={ocrBlocksQuery.data ?? []} />
              </div>
            </Document>
          )}
        </div>

        {hasSearch ? (
          <SearchResults
            activeIndex={activeMatchIndex}
            isError={searchQuery.isError}
            isLoading={searchQuery.isLoading}
            result={searchQuery.data}
            onActivate={activateMatch}
          />
        ) : null}
      </div>
    </div>
  );
}

function OcrHighlightOverlay({ blocks }: { blocks: OcrTextBlock[] }) {
  if (!blocks.length) return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden rounded-sm"
    >
      {blocks.map((block, index) => (
        <span
          className="absolute rounded-[2px] border border-amber-500/70 bg-amber-300/35 mix-blend-multiply dark:mix-blend-normal"
          key={`${block.page_number}-${block.left_ratio}-${block.top_ratio}-${index}`}
          style={{
            left: `${block.left_ratio * 100}%`,
            top: `${block.top_ratio * 100}%`,
            width: `${block.width_ratio * 100}%`,
            height: `${block.height_ratio * 100}%`,
          }}
          title={block.text}
        />
      ))}
    </div>
  );
}

function SearchResults({
  activeIndex,
  isError,
  isLoading,
  result,
  onActivate,
}: {
  activeIndex: number;
  isError: boolean;
  isLoading: boolean;
  result: DocumentTextSearchResult | undefined;
  onActivate: (index: number) => void;
}) {
  if (isError) {
    return (
      <aside className="border-t border-border p-5 lg:border-l lg:border-t-0">
        <p className="text-sm font-medium">Search unavailable</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          PaperVault could not search this document. Try again after checking
          the API connection.
        </p>
      </aside>
    );
  }
  if (isLoading) {
    return (
      <aside className="border-t border-border p-4 text-sm text-muted-foreground lg:border-l lg:border-t-0">
        Searching...
      </aside>
    );
  }
  if (!result?.matches.length) {
    return (
      <aside className="border-t border-border p-5 lg:border-l lg:border-t-0">
        <p className="text-sm font-medium">No matches found</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Try a shorter word or phrase from the document.
        </p>
      </aside>
    );
  }

  return (
    <aside className="min-w-0 border-t border-border bg-card lg:border-l lg:border-t-0">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-sm font-medium">
            {result.total_matches}{" "}
            {result.total_matches === 1 ? "match" : "matches"}
          </p>
          {!result.page_mapping_available ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Reprocess to enable page navigation
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <ViewerIconButton
            label="Previous match"
            disabled={activeIndex <= 0}
            onClick={() => onActivate(activeIndex - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </ViewerIconButton>
          <ViewerIconButton
            label="Next match"
            disabled={activeIndex >= result.matches.length - 1}
            onClick={() => onActivate(activeIndex + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </ViewerIconButton>
        </div>
      </div>
      <div className="max-h-[620px] space-y-1 overflow-y-auto p-2">
        {result.matches.map((match, index) => (
          <button
            className={cn(
              "w-full rounded-md px-3 py-2.5 text-left text-xs leading-5 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              index === activeIndex && "bg-muted",
            )}
            key={`${match.page_number ?? "legacy"}-${index}`}
            type="button"
            onClick={() => onActivate(index)}
          >
            <span className="mb-1 block font-medium text-muted-foreground">
              {match.page_number
                ? `Page ${match.page_number}`
                : `Match ${index + 1}`}
            </span>
            <span>{match.before}</span>
            <mark className="rounded-sm bg-amber-200 px-0.5 text-amber-950">
              {match.match}
            </mark>
            <span>{match.after}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

function ViewerIconButton({
  label,
  children,
  disabled,
  onClick,
}: {
  label: string;
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      aria-label={label}
      className="h-8 w-8"
      disabled={disabled}
      size="icon"
      type="button"
      variant="ghost"
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function PreviewUnavailable() {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-lg border border-dashed border-border bg-muted/40 p-8 text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-background text-muted-foreground">
          <FileText className="h-5 w-5" aria-hidden="true" />
        </div>
        <p className="mt-4 text-sm font-medium">Preview not ready</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          The original file is saved, but a clean preview is available only
          after processing completes successfully.
        </p>
      </div>
    </div>
  );
}

function PreviewMessage({ message }: { message: string }) {
  return (
    <div className="flex min-h-64 w-full items-center justify-center p-5 text-sm text-muted-foreground">
      {message}
    </div>
  );
}
