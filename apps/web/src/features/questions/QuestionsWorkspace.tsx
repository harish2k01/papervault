import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowUp,
  FileText,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import { askQuestion } from "../../lib/api";

const exampleQuestions = [
  "What was my salary in August 2022?",
  "Show my insurance policies and their expiry dates.",
  "When did I purchase my iPad?",
];

export function QuestionsWorkspace({
  onOpenDocument,
}: {
  onOpenDocument: (documentId: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const questionMutation = useMutation({ mutationFn: askQuestion });

  function submitQuestion(event?: FormEvent) {
    event?.preventDefault();
    const normalized = question.trim();
    if (normalized.length < 3 || questionMutation.isPending) {
      return;
    }
    questionMutation.mutate(normalized);
  }

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <h1 className="text-2xl font-semibold">Ask PaperVault</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers use only evidence found in your documents.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-8 xl:px-7">
        <div className="mx-auto max-w-3xl">
          <form className="relative" onSubmit={submitQuestion}>
            <label className="sr-only" htmlFor="vault-question">
              Ask a question about your documents
            </label>
            <textarea
              className="min-h-28 w-full resize-none rounded-lg border border-input bg-card px-4 py-4 pr-14 text-base text-foreground shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
              id="vault-question"
              maxLength={1000}
              placeholder="Ask about a salary, purchase, policy, due date, or any document..."
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submitQuestion();
                }
              }}
            />
            <Button
              aria-label="Ask question"
              className="absolute bottom-3 right-3"
              disabled={
                question.trim().length < 3 || questionMutation.isPending
              }
              size="icon"
              type="submit"
            >
              <ArrowUp className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>

          {!questionMutation.data ? (
            <div className="mt-5 flex flex-wrap gap-2">
              {exampleQuestions.map((example) => (
                <button
                  className="rounded-full border border-border bg-card px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                  key={example}
                  type="button"
                  onClick={() => setQuestion(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          ) : null}

          {questionMutation.isPending ? (
            <div className="mt-10 flex items-center gap-3 text-sm text-muted-foreground">
              <MessageSquareText
                className="h-5 w-5 animate-pulse"
                aria-hidden="true"
              />
              Retrieving supporting pages...
            </div>
          ) : null}

          {questionMutation.error instanceof Error ? (
            <p
              className="mt-8 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
              role="alert"
            >
              {questionMutation.error.message}
            </p>
          ) : null}

          {questionMutation.data ? (
            <div className="mt-9 space-y-8">
              <section aria-live="polite">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <ShieldCheck
                      className="h-4 w-4 text-primary"
                      aria-hidden="true"
                    />
                    <h2 className="text-sm font-semibold">
                      {questionMutation.data.answered
                        ? "Grounded answer"
                        : "No supported answer"}
                    </h2>
                  </div>
                  {questionMutation.data.answered ? (
                    <span className="text-xs text-muted-foreground">
                      {Math.round(questionMutation.data.confidence_score * 100)}
                      % confidence
                    </span>
                  ) : null}
                </div>
                <p className="text-base leading-7">
                  {questionMutation.data.answer ??
                    questionMutation.data.refusal_reason}
                </p>
              </section>

              {questionMutation.data.citations.length > 0 ? (
                <section>
                  <h2 className="mb-3 text-sm font-semibold">Sources</h2>
                  <div className="space-y-2">
                    {questionMutation.data.citations.map((citation) => (
                      <button
                        className="flex w-full gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/40"
                        key={`${citation.document_id}-${citation.page_number}`}
                        type="button"
                        onClick={() => onOpenDocument(citation.document_id)}
                      >
                        <FileText
                          className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                          aria-hidden="true"
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">
                            {citation.document_title} - Page{" "}
                            {citation.page_number}
                          </span>
                          <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                            {citation.snippet}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
