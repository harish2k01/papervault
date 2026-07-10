import { useMemo, useState } from "react";
import {
  AlertCircle,
  Bell,
  CalendarClock,
  CheckCircle2,
  Inbox,
  type LucideIcon,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import {
  DocumentItem,
  NotificationItem,
  NotificationStatus,
} from "../../lib/api";
import { cn } from "../../lib/utils";
import {
  compareNotifications,
  formatDateOnly,
  formatNotificationKind,
  getDueState,
  getNotificationStats,
} from "./notification-utils";

type NotificationFilter = "pending" | "all" | "read" | "dismissed";

export function NotificationsWorkspace({
  notifications,
  documents,
  isLoading,
  isUpdating,
  error,
  onOpenDocument,
  onUpdateStatus,
}: {
  notifications: NotificationItem[];
  documents: DocumentItem[];
  isLoading: boolean;
  isUpdating: boolean;
  error: string | null;
  onOpenDocument: (documentId: string | null) => void;
  onUpdateStatus: (notificationId: string, status: NotificationStatus) => void;
}) {
  const [filter, setFilter] = useState<NotificationFilter>("pending");
  const documentsById = useMemo(
    () => new Map(documents.map((document) => [document.id, document])),
    [documents],
  );
  const stats = useMemo(
    () => getNotificationStats(notifications),
    [notifications],
  );
  const visibleNotifications = useMemo(() => {
    const matchingNotifications = notifications
      .filter((notification) => notificationMatchesFilter(notification, filter))
      .sort(compareNotifications);
    return matchingNotifications;
  }, [filter, notifications]);

  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Reminder center
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal">
              Notifications
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              Track expiry dates, policy renewals, due dates, and warranty
              reminders extracted from document metadata.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
            <span className="font-semibold">{stats.pending}</span>
            <span className="ml-1 text-muted-foreground">pending</span>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-7">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <NotificationStatCard
            icon={AlertCircle}
            label="Overdue"
            value={stats.overdue}
            tone="danger"
          />
          <NotificationStatCard
            icon={CalendarClock}
            label="Due in 30 days"
            value={stats.dueSoon}
            tone="warning"
          />
          <NotificationStatCard
            icon={Bell}
            label="Pending"
            value={stats.pending}
          />
          <NotificationStatCard
            icon={CheckCircle2}
            label="Handled"
            value={stats.handled}
          />
        </div>

        <section className="mt-6 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex flex-col gap-4 border-b border-border p-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-semibold">Reminder queue</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Review reminders and clear the queue without leaving the vault.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(["pending", "all", "read", "dismissed"] as const).map(
                (option) => (
                  <button
                    className={cn(
                      "rounded-md px-3 py-1.5 text-sm transition-colors",
                      filter === option
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground",
                    )}
                    key={option}
                    type="button"
                    onClick={() => setFilter(option)}
                  >
                    {option === "all" ? "All" : titleCase(option)}
                  </button>
                ),
              )}
            </div>
          </div>

          {error ? (
            <p
              className="m-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <div className="divide-y divide-border">
            {isLoading ? (
              <div className="p-4">
                <NotificationListSkeleton />
              </div>
            ) : visibleNotifications.length === 0 ? (
              <NotificationEmptyState filter={filter} />
            ) : (
              visibleNotifications.map((notification) => (
                <NotificationRow
                  key={notification.id}
                  notification={notification}
                  document={
                    notification.document_id
                      ? documentsById.get(notification.document_id)
                      : undefined
                  }
                  disabled={isUpdating}
                  onOpenDocument={() =>
                    onOpenDocument(notification.document_id)
                  }
                  onUpdateStatus={(status) =>
                    onUpdateStatus(notification.id, status)
                  }
                />
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function NotificationStatCard({
  icon: Icon,
  label,
  value,
  tone = "default",
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  tone?: "default" | "warning" | "danger";
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg",
            tone === "danger"
              ? "bg-rose-50 text-rose-700"
              : tone === "warning"
                ? "bg-amber-50 text-amber-700"
                : "bg-muted text-muted-foreground",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function NotificationRow({
  notification,
  document,
  disabled,
  onOpenDocument,
  onUpdateStatus,
}: {
  notification: NotificationItem;
  document: DocumentItem | undefined;
  disabled: boolean;
  onOpenDocument: () => void;
  onUpdateStatus: (status: NotificationStatus) => void;
}) {
  const dueState = getDueState(notification.due_date);
  const sourceField =
    typeof notification.payload.source_field === "string"
      ? notification.payload.source_field.replaceAll("_", " ")
      : null;

  return (
    <article className="p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium",
                notification.status === "pending"
                  ? dueState.tone === "danger"
                    ? "bg-rose-50 text-rose-800"
                    : dueState.tone === "warning"
                      ? "bg-amber-50 text-amber-800"
                      : "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {dueState.label}
            </span>
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs capitalize text-muted-foreground">
              {formatNotificationKind(notification.kind)}
            </span>
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs capitalize text-muted-foreground">
              {notification.status}
            </span>
          </div>
          <h3 className="mt-3 break-words text-sm font-semibold">
            {notification.title}
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
            {notification.message}
          </p>
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>Due {formatDateOnly(notification.due_date)}</span>
            {document ? <span>{document.title}</span> : null}
            {sourceField ? <span>From {sourceField}</span> : null}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          {document ? (
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={onOpenDocument}
            >
              Open document
            </Button>
          ) : null}
          {notification.status !== "pending" ? (
            <Button
              size="sm"
              variant="secondary"
              type="button"
              disabled={disabled}
              onClick={() => onUpdateStatus("pending")}
            >
              Reopen
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              type="button"
              disabled={disabled}
              onClick={() => onUpdateStatus("read")}
            >
              Mark read
            </Button>
          )}
          {notification.status !== "dismissed" ? (
            <Button
              size="sm"
              type="button"
              disabled={disabled}
              onClick={() => onUpdateStatus("dismissed")}
            >
              Dismiss
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function NotificationEmptyState({ filter }: { filter: NotificationFilter }) {
  return (
    <div className="flex min-h-[320px] items-center justify-center p-8 text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Inbox className="h-5 w-5" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">
          {filter === "pending" ? "No pending reminders" : "No reminders here"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {filter === "pending"
            ? "PaperVault will show due dates, expiries, and renewals here after metadata extraction or manual refresh."
            : "Change the filter or refresh reminders from a document detail view."}
        </p>
      </div>
    </div>
  );
}

function NotificationListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div className="h-28 animate-pulse rounded-lg bg-muted" key={index} />
      ))}
    </div>
  );
}

function notificationMatchesFilter(
  notification: NotificationItem,
  filter: NotificationFilter,
) {
  return filter === "all" || notification.status === filter;
}

function titleCase(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}
