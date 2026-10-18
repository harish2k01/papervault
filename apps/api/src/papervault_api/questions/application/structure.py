"""Preserve Docling reading order, page provenance and table header/row relationships."""

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Passage:
    page: int
    kind: str
    section: str
    text: str
    provenance: list[dict[str, Any]]


def split_text(text: str, limit: int = 700) -> list[str]:
    """Byte bounded pieces, preferring sentence/word boundaries; never discard a tail."""
    text = text.strip()
    parts: list[str] = []
    while text:
        if len(text.encode()) <= limit:
            parts.append(text)
            break
        prefix = text.encode()[:limit].decode(errors="ignore")
        boundaries = [match.end() for match in re.finditer(r"[.!?;]\s|\n", prefix)]
        cut = (
            boundaries[-1]
            if boundaries and boundaries[-1] > len(prefix) // 2
            else prefix.rfind(" ")
        )
        if cut <= 0:
            cut = len(prefix)
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return parts


def structured_passages(document: dict[str, Any]) -> list[Passage]:
    passages: list[Passage] = []
    headings: dict[int, str] = {}
    visited: set[str] = set()

    def resolve(reference: str) -> dict[str, Any]:
        item: Any = document
        for part in reference.removeprefix("#/").split("/"):
            item = item[int(part)] if isinstance(item, list) else item[part]
        if not isinstance(item, dict):
            raise ValueError("Invalid structured item")
        return item

    def visit(item: dict[str, Any]) -> None:
        reference = item.get("$ref")
        if isinstance(reference, str):
            if reference in visited:
                return
            visited.add(reference)
            item = resolve(reference)
        kind = str(item.get("label", "group"))
        provenance = item.get("prov", [])
        if not isinstance(provenance, list):
            raise ValueError("Invalid page provenance")
        text = str(item.get("text", "")).strip()
        if kind in {"section_header", "title"} and text:
            level = max(1, min(8, int(item.get("level", 1))))
            for old_level in list(headings):
                if old_level >= level:
                    del headings[old_level]
            headings[level] = text
        section = " / ".join(headings.values())
        # A bounded breadcrumb leaves room for the source text in 512-token models.
        section = section.encode()[:200].decode(errors="ignore")
        if kind == "table":
            data = item.get("data", {})
            cells = data.get("table_cells", [])
            headers = [str(cell.get("text", "")) for cell in cells if cell.get("column_header")]
            rows: dict[int, list[str]] = {}
            for cell in cells:
                if not cell.get("column_header"):
                    row = int(cell.get("start_row_offset_idx", 0))
                    rows.setdefault(row, []).append(str(cell.get("text", "")))
            header = " | ".join(headers)
            header_prefix = "Columns: " + header + "\n"
            if len(header_prefix.encode()) > 300:
                raise ValueError("Table header exceeds the supported passage budget")
            texts = [
                header_prefix + piece
                for row in rows.values()
                for piece in split_text(" | ".join(row), 700 - len(header_prefix.encode()))
            ]
            if not texts and header:
                texts = [header]
        else:
            texts = [text] if text else []
        if texts:
            if not provenance:
                raise ValueError("Structured text has no page provenance")
            # Multi-page table provenance is retained. Assign rows only when provenance is
            # unambiguous; otherwise flag conversion for review rather than invent a page.
            pages = {int(prov["page_no"]) for prov in provenance}
            if len(pages) != 1 or min(pages) < 1:
                raise ValueError("Structured item has ambiguous page provenance")
            page = next(iter(pages))
            for block in texts:
                for piece in split_text(block):
                    passages.append(Passage(page, kind, section, piece, provenance))
        for child in item.get("children", []):
            visit(child)
        for key in ("captions", "footnotes"):
            for related in item.get(key, []):
                visit(related)

    visit(document.get("body", {}))
    return passages
