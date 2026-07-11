import { FileText, History } from "lucide-react";

import { Button } from "../../components/ui/button";
import { VaultTimelineItem } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";

export function TimelineWorkspace({
  events,
  isLoading,
  onOpenDocument,
}: {
  events: VaultTimelineItem[];
  isLoading: boolean;
  onOpenDocument: (documentId: string) => void;
}) {
  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-4 xl:px-8">
        <h1 className="text-xl font-semibold">Activity</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Changes across your document library.
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-8">
        <div className="mx-auto max-w-4xl">
          {isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((item) => (
                <div
                  className="h-20 animate-pulse rounded-lg bg-muted"
                  key={item}
                />
              ))}
            </div>
          ) : events.length ? (
            <div className="border-l border-border pl-6">
              {events.map((event) => (
                <article className="relative pb-7 last:pb-0" key={event.id}>
                  <span className="absolute -left-[29px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background bg-primary" />
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">
                        {humanizeLabel(event.event_type)}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(event.occurred_at).toLocaleString()}
                      </p>
                    </div>
                    {event.document_id ? (
                      <Button
                        size="sm"
                        type="button"
                        variant="ghost"
                        onClick={() => onOpenDocument(event.document_id!)}
                      >
                        <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                        {event.document_title || "Open document"}
                      </Button>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border py-16 text-center">
              <History className="mx-auto h-6 w-6 text-muted-foreground" />
              <h2 className="mt-3 text-sm font-semibold">No activity yet</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Uploads and document changes will appear here.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
