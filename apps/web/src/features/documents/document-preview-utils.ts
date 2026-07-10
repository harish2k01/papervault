export function renderHighlightedText(text: string, query: string) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    return escapeHtml(text);
  }

  const pattern = new RegExp(escapeRegExp(normalizedQuery), "gi");
  let output = "";
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    output += escapeHtml(text.slice(cursor, index));
    output += `<mark class="papervault-pdf-highlight">${escapeHtml(match[0])}</mark>`;
    cursor = index + match[0].length;
  }
  return output + escapeHtml(text.slice(cursor));
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
