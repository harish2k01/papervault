import { useState } from "react";
import { Tags } from "lucide-react";

import { Button } from "../../components/ui/button";
import { TagItem } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";

export function TagsWorkspace({
  tags,
  isLoading,
  isCreating,
  error,
  onCreateTag,
}: {
  tags: TagItem[];
  isLoading: boolean;
  isCreating: boolean;
  error: string | null;
  onCreateTag: (name: string) => void;
}) {
  const [tagName, setTagName] = useState("");

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Vault taxonomy
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal">
              Tags
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              Keep folders optional. Use manual and AI-assisted tags to build
              durable document collections.
            </p>
          </div>
          <form
            className="flex w-full max-w-md gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              onCreateTag(tagName);
              setTagName("");
            }}
          >
            <input
              className="h-10 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Create tag"
              value={tagName}
              disabled={isCreating}
              onChange={(event) => setTagName(event.target.value)}
            />
            <Button type="submit" disabled={isCreating || !tagName.trim()}>
              Create
            </Button>
          </form>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-7">
        {error ? (
          <p
            className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {isLoading ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                className="h-24 animate-pulse rounded-xl border border-border bg-card"
                key={index}
              />
            ))}
          </div>
        ) : tags.length === 0 ? (
          <div className="flex min-h-[420px] items-center justify-center rounded-xl border border-dashed border-border bg-card p-8 text-center">
            <div className="max-w-sm">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <Tags className="h-5 w-5" aria-hidden="true" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">No tags yet</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Create a reusable tag here, or accept suggested tags from a
                document after AI processing.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {tags.map((tag) => (
              <article
                className="rounded-xl border border-border bg-card p-4 shadow-sm"
                key={tag.id}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-sm font-semibold">
                      {humanizeLabel(tag.name)}
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {humanizeLabel(tag.source)} tag
                    </p>
                  </div>
                  <span
                    className="h-3 w-3 shrink-0 rounded-full border border-border"
                    style={{
                      backgroundColor: tag.color ?? "hsl(var(--primary))",
                    }}
                  />
                </div>
                {tag.description ? (
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">
                    {tag.description}
                  </p>
                ) : (
                  <p className="mt-3 text-sm leading-6 text-muted-foreground">
                    Use this tag from document detail to build a collection.
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
