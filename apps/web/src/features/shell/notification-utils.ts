import { NotificationItem } from "../../lib/api";

export function formatDateOnly(value: string) {
  return parseDateOnly(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function compareNotifications(
  left: NotificationItem,
  right: NotificationItem,
) {
  const leftStatusRank = left.status === "pending" ? 0 : 1;
  const rightStatusRank = right.status === "pending" ? 0 : 1;
  if (leftStatusRank !== rightStatusRank) {
    return leftStatusRank - rightStatusRank;
  }
  return (
    parseDateOnly(left.due_date).getTime() -
    parseDateOnly(right.due_date).getTime()
  );
}

export function getDueState(dueDate: string) {
  const daysUntilDue = getDaysUntilDue(dueDate);
  if (daysUntilDue < 0) {
    return {
      label: `Overdue by ${Math.abs(daysUntilDue)}d`,
      tone: "danger" as const,
    };
  }
  if (daysUntilDue === 0) {
    return { label: "Due today", tone: "warning" as const };
  }
  if (daysUntilDue <= 30) {
    return { label: `Due in ${daysUntilDue}d`, tone: "warning" as const };
  }
  return { label: `Due in ${daysUntilDue}d`, tone: "default" as const };
}

export function formatNotificationKind(kind: string) {
  return kind.replaceAll("_", " ");
}

export function getNotificationStats(notifications: NotificationItem[]) {
  return notifications.reduce(
    (stats, notification) => {
      if (notification.status === "pending") {
        stats.pending += 1;
        const daysUntilDue = getDaysUntilDue(notification.due_date);
        if (daysUntilDue < 0) {
          stats.overdue += 1;
        } else if (daysUntilDue <= 30) {
          stats.dueSoon += 1;
        }
      } else {
        stats.handled += 1;
      }
      return stats;
    },
    { overdue: 0, dueSoon: 0, pending: 0, handled: 0 },
  );
}

function getDaysUntilDue(value: string) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round(
    (parseDateOnly(value).getTime() - today.getTime()) / 86_400_000,
  );
}

function parseDateOnly(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return new Date(value);
  }
  return new Date(year, month - 1, day);
}
