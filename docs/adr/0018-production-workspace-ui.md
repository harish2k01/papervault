# ADR 0018: Production Workspace UI

## Status

Accepted

## Context

The first web shell was functional but looked like an implementation scaffold:
flat navigation, weak hierarchy, plain empty states, and a document detail pane
that collapsed to a single text line when nothing was selected. That made the
application feel less production-ready even though the backend workflows were
usable.

## Decision

Refresh the workspace UI while preserving the existing frontend data flow:

- Use a focused empty-vault mode before the document list has content, then keep
  the three-pane information architecture for navigation, document search/list,
  and document review.
- Add active navigation, vault health metrics, richer document cards, and
  restrained empty states that avoid repeating the same upload prompt.
- Keep search focused on one primary query input, with advanced filters behind an
  expandable panel.
- Hide saved and recent search shortcuts until there are useful entries to show.
- Replace the populated document view with a reader-first surface: identity,
  bounded preview/status, summary, extracted fields, tags, signals, timeline,
  and versions.
- Keep edit forms and raw metadata available, but place them behind disclosure
  controls so they do not dominate normal review.
- Failed or processing documents render a bounded status panel instead of
  embedding the PDF viewer.
- Keep the desktop workspace viewport-bound so navigation, the document list,
  and document review remain stable while their own content scrolls.
- Mount advanced controls only after explicit user intent, including saved
  search creation, manual tag management, document field editing, and raw JSON
  editing.
- Improve design tokens and the button primitive, but keep most presentation
  components local to the shell for now.

## Consequences

The app now has a more credible operational workspace without introducing a
large design-system abstraction too early. The shell is still a large component,
so future phases should extract stable sections only after workflows settle. The
visual refresh does not alter API contracts, search behavior, authentication, or
document lifecycle logic.
