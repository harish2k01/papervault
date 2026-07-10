# ADR 0019: Notification Workflow UI

## Status

Accepted

## Context

PaperVault already generated notification records from document metadata, but the web app only displayed a count. That made expiry, renewal, warranty, and due-date records hard to review or clear. The sync path also created new reminders without retiring stale reminders when metadata changed.

## Decision

Add a dedicated Notifications workspace to the React shell. The workspace lists reminders, exposes status filters, shows overdue and due-soon totals, links back to the source document, and lets users mark reminders as read, dismissed, or pending.

Document detail remains focused on the selected document. It shows document-specific reminder counts and active reminder cards, plus a manual refresh action that regenerates reminders from current metadata.

Treat notifications as a metadata-derived projection. Sync upserts current reminders and dismisses stale reminders for managed date fields.

## Consequences

- Users can triage reminders without editing raw metadata or leaving the app shell.
- Stale metadata dates no longer leave active reminder records behind.
- The shell now owns multiple workspace views. A router-level split is still deferred until navigation depth increases.
- Dismissed reminders are preserved for audit/history instead of being deleted.
