import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { documentIntelligence } from "../../lib/api";

export function DocumentIntelligence({
  documentId,
  onPage,
}: {
  documentId: string;
  onPage: (page: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["document-intelligence", documentId],
    queryFn: () => documentIntelligence(documentId),
    enabled: open,
    refetchInterval: open ? 15_000 : false,
  });
  const data = query.data;
  const findings = data?.understanding?.findings ?? [];
  return (
    <details
      className="rounded-lg border border-border p-4"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-semibold">
        Document intelligence preview
      </summary>
      {open ? (
        <div className="mt-3 space-y-3 text-sm">
          <p className="text-xs text-muted-foreground">
            Structured facts, duties, conditions and exclusions from the local
            analysis pipeline. Quotes are checked against the source; model
            labels and completeness require review.
          </p>
          {query.isPending ? <p>Loading analysis…</p> : null}
          {query.isError ? (
            <p role="alert">The local analysis preview is unavailable.</p>
          ) : null}
          {data?.status === "disabled" ? (
            <p>Document intelligence preview is not enabled.</p>
          ) : null}
          {data?.status === "not_indexed" ? (
            <p>
              The structured index is not ready. Your original and text search
              remain available.
            </p>
          ) : null}
          {data?.status === "ready" ? (
            <p className="text-xs text-muted-foreground">
              {data.covered_pages?.length ?? 0} of {data.page_count} pages
              contain indexed text.{" "}
              {data.understanding?.status
                ? `${data.understanding.covered_passages ?? 0} passages analysed.`
                : "Fact analysis is queued or running."}
            </p>
          ) : null}
          {data?.understanding?.status && !findings.length ? (
            <p>
              {data.understanding.status === "processing"
                ? "Analysing the document's facts and conditions…"
                : data.understanding.status === "failed"
                  ? "Local fact analysis failed. Regenerate the document to retry."
                  : "No verified facts were returned. Review the source document."}
            </p>
          ) : null}
          {findings.map((finding, index) => (
            <article
              key={`${finding.ordinal}-${index}`}
              className="rounded-lg bg-muted/40 p-3"
            >
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {finding.kind}
              </p>
              <h4 className="mt-1 font-medium">{finding.label}</h4>
              <p className="mt-1 whitespace-pre-wrap leading-6">
                {finding.value}
              </p>
              <details className="mt-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer">Source evidence</summary>
                <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-primary/40 pl-3 leading-5">
                  {finding.quote}
                </blockquote>
              </details>
              <button
                className="mt-2 text-xs font-medium text-primary underline"
                type="button"
                onClick={() => onPage(finding.page_number)}
              >
                View page {finding.page_number}
              </button>
            </article>
          ))}
        </div>
      ) : null}
      {data?.status === "building" ? (
        <p>Reading the document layout and building its semantic index…</p>
      ) : null}
      {data?.status === "failed" ? (
        <p role="alert">
          Structured indexing failed. Regenerate this document to retry; its
          original and text search remain available.
        </p>
      ) : null}
    </details>
  );
}
