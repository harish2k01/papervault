import { describe, expect, it } from "vitest";

import { renderHighlightedText } from "./document-preview-utils";

describe("renderHighlightedText", () => {
  it("highlights case-insensitive literal matches", () => {
    expect(renderHighlightedText("Salary and salary", "salary")).toBe(
      '<mark class="papervault-pdf-highlight">Salary</mark> and <mark class="papervault-pdf-highlight">salary</mark>',
    );
  });

  it("escapes document content and regex characters", () => {
    expect(renderHighlightedText("<script> total.* due", ".*")).toBe(
      '&lt;script&gt; total<mark class="papervault-pdf-highlight">.*</mark> due',
    );
  });
});
