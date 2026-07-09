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

- Keep the three-pane information architecture for navigation, document
  search/list, and document review.
- Add active navigation, vault health metrics, richer document cards, and
  production-grade empty states.
- Keep search focused on one primary query input, with advanced filters behind an
  expandable panel.
- Replace the blank document detail placeholder with an overview surface that
  explains the next useful actions.
- Improve design tokens and the button primitive, but keep most presentation
  components local to the shell for now.

## Consequences

The app now has a more credible operational workspace without introducing a
large design-system abstraction too early. The shell is still a large component,
so future phases should extract stable sections only after workflows settle. The
visual refresh does not alter API contracts, search behavior, authentication, or
document lifecycle logic.
