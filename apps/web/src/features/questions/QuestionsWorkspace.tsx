import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowUp,
  FileText,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import { askQuestion } from "../../lib/api";

const exampleQuestions = [
  "What was the net pay in my latest payslip?",
  "Show my insurance policies and their expiry dates.",
  "When did I purchase my iPad?",
];

export function QuestionsWorkspace({
  onOpenDocument,
}: {
  onOpenDocument: (documentId: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const questionMutation = useMutation({ mutationFn: askQuestion });

  function submitQuestion(event?: FormEvent) {
    event?.preventDefault();
    const normalized = question.trim();
    if (normalized.length < 3 || questionMutation.isPending) return;
    setSubmittedQuestion(normalized);
    questionMutation.mutate(normalized);
  }

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-4 xl:px-8">
        <div className="mx-auto max-w-4xl">
          <h1 className="text-xl font-semibold">Ask PaperVault</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Answers are grounded in your documents and include their sources.
          </p>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-8 xl:px-8">
        <div className="mx-auto max-w-4xl">
          {!questionMutation.data && !questionMutation.isPending ? (
            <div className="flex min-h-[52vh] flex-col items-center justify-center text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Sparkles className="h-5 w-5" aria-hidden="true" />
              </div>
              <h2 className="mt-5 text-xl font-semibold">
                Ask your document library
              </h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                PaperVault retrieves the most relevant pages and answers only
                when the evidence supports a response.
              </p>
              <div className="mt-7 grid w-full max-w-2xl gap-2 sm:grid-cols-3">
                {exampleQuestions.map((example) => (
                  <button
                    className="rounded-lg border border-border bg-card p-3 text-left text-sm leading-5 text-muted-foreground transition-colors hover:border-primary/40 hover:bg-muted/40 hover:text-foreground"
                    key={example}
                    type="button"
                    onClick={() => setQuestion(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {submittedQuestion &&
          (questionMutation.data || questionMutation.isPending) ? (
            <div className="space-y-7 pb-5">
              <div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-muted px-4 py-3 text-sm">
                {submittedQuestion}
              </div>

              {questionMutation.isPending ? (
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <MessageSquareText
                    className="h-5 w-5 animate-pulse text-primary"
                    aria-hidden="true"
                  />
                  Finding the strongest supporting evidence...
                </div>
              ) : null}

              {questionMutation.data ? (
                <article aria-live="polite">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                    </div>
                    <div>
                      <h2 className="text-sm font-semibold">
                        {questionMutation.data.answered
                          ? "Grounded answer"
                          : "No supported answer"}
                      </h2>
                      {questionMutation.data.answered ? (
                        <p className="text-xs text-muted-foreground">
                          {Math.round(
                            questionMutation.data.confidence_score * 100,
                          )}
                          % confidence
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-4 max-w-3xl text-base leading-7">
                    {questionMutation.data.answer ??
                      questionMutation.data.refusal_reason}
                  </p>

                  {questionMutation.data.citations.length ? (
                    <details className="mt-6" open>
                      <summary className="cursor-pointer text-sm font-semibold">
                        {questionMutation.data.citations.length} supporting
                        {questionMutation.data.citations.length === 1
                          ? " source"
                          : " sources"}
                      </summary>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {questionMutation.data.citations.map((citation) => (
                          <button
                            aria-label={`${citation.document_title} - Page ${citation.page_number}`}
                            className="flex min-w-0 gap-3 rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/40"
                            key={`${citation.document_id}-${citation.page_number}`}
                            type="button"
                            onClick={() => onOpenDocument(citation.document_id)}
                          >
                            <FileText
                              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                              aria-hidden="true"
                            />
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-medium">
                                {citation.document_title}
                              </span>
                              <span className="block text-xs text-muted-foreground">
                                Page {citation.page_number}
                              </span>
                              <span className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                                {citation.snippet}
                              </span>
                            </span>
                          </button>
                        ))}
                      </div>
                    </details>
                  ) : null}
                </article>
              ) : null}
            </div>
          ) : null}

          {questionMutation.error instanceof Error ? (
            <p
              className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
              role="alert"
            >
              {questionMutation.error.message}
            </p>
          ) : null}
        </div>
      </div>

      <div className="border-t border-border bg-background/95 px-5 py-4 backdrop-blur xl:px-8">
        <form className="relative mx-auto max-w-4xl" onSubmit={submitQuestion}>
          <label className="sr-only" htmlFor="vault-question">
            Ask a question about your documents
          </label>
          <textarea
            className="max-h-40 min-h-14 w-full resize-none rounded-xl border border-input bg-card px-4 py-4 pr-14 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            id="vault-question"
            maxLength={1000}
            rows={1}
            placeholder="Ask a question about your documents"
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
            className="absolute bottom-2 right-2"
            disabled={question.trim().length < 3 || questionMutation.isPending}
            size="icon"
            type="submit"
          >
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      </div>
    </section>
  );
}
