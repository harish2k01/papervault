"""Source references and typed values that do not depend on generated quote text."""

import json
import re
from dataclasses import dataclass
from typing import Any

from papervault_api.documents.domain.document_types import (
    MetadataFieldDefinition,
    MetadataFieldType,
)
from papervault_api.documents.infrastructure.ai import FIELD_PATTERNS


@dataclass(frozen=True)
class SourceLine:
    number: int
    text: str
    start: int
    end: int


def numbered_lines(text: str) -> tuple[SourceLine, ...]:
    lines: list[SourceLine] = []
    cursor = 0
    for raw in text.splitlines(keepends=True):
        offset = 0
        while offset < len(raw):
            end = min(len(raw), offset + 700)
            if end < len(raw):
                boundary = raw.rfind(" ", offset, end)
                if boundary > offset + 350:
                    end = boundary + 1
            value = raw[offset:end].rstrip("\r\n")
            if value.strip():
                lines.append(
                    SourceLine(len(lines) + 1, value, cursor + offset, cursor + offset + len(value))
                )
            offset = end
        cursor += len(raw)
    return tuple(lines)


def line_batches(
    windows: tuple[str, ...], user_budget: int
) -> tuple[tuple[str, tuple[SourceLine, ...]], ...]:
    if user_budget < 512:
        raise ValueError("Model context cannot fit the analysis contract and output budget")
    pending = list(reversed(windows))
    batches = []
    while pending:
        window = pending.pop()
        lines = numbered_lines(window)
        if not lines:
            continue
        serialized = json.dumps({line.number: line.text for line in lines}, ensure_ascii=False)
        if len(serialized.encode()) + 128 > user_budget:
            middle = len(window) // 2
            overlap = min(100, middle // 4)
            pending.extend([window[middle - overlap :], window[:middle]])
        else:
            batches.append((window, lines))
    return tuple(batches)


def referenced_quote(references: object, lines: tuple[SourceLine, ...], source: str) -> str | None:
    if not isinstance(references, list) or not references:
        return None
    if any(type(number) is not int or not 1 <= number <= len(lines) for number in references):
        return None
    first, last = lines[min(references) - 1], lines[max(references) - 1]
    return source[first.start : last.end]


def labelled_value(field: MetadataFieldDefinition, quote: str, suggested: object) -> object:
    aliases = {field.label, field.key.replace("_", " ")}
    for patterns in FIELD_PATTERNS.values():
        aliases.update(patterns.get(field.key, ()))
    for alias in sorted(aliases, key=len, reverse=True):
        match = re.search(r"\b" + re.escape(alias) + r"\b", quote, flags=re.I)
        if not match:
            continue
        tail = quote[match.end() :].lstrip(" \t\r\n:#")
        if tail.startswith(("- ", "\u2013 ", "\u2014 ")):
            tail = tail[2:]
        first_line = tail.splitlines()[0] if tail else ""
        if field.field_type is MetadataFieldType.STRING:
            if (
                isinstance(suggested, str)
                and suggested
                and re.search(r"(?<!\w)" + re.escape(suggested) + r"(?!\w)", first_line, flags=re.I)
            ):
                return suggested
            return first_line.strip()
        if field.field_type is not MetadataFieldType.OBJECT_LIST:
            return first_line.strip()
    return suggested


def action_topics(text: str) -> tuple[str, ...]:
    topics = []
    for match in re.finditer(
        r"\b(?:policy|coverage|cover|offer|contract|agreement)\s+"
        r"(?:(?:has|have)\s+been\s+|(?:was|were|is|are|stands)\s+)?"
        r"(cancelled|canceled|withdrawn|terminated|revoked)\b",
        text,
        flags=re.I,
    ):
        prefix = text[max(0, match.start() - 40) : match.start()]
        if re.search(r"\b(?:if|when|unless|may|might|could|should)\b", prefix, flags=re.I):
            continue
        word = match.group(1).casefold()
        topics.append(
            "cancellation"
            if word in {"cancelled", "canceled"}
            else "withdrawal"
            if word == "withdrawn"
            else "termination"
        )
    return tuple(dict.fromkeys(topics))


def labelled_candidates(
    fields: dict[str, MetadataFieldDefinition], source: str
) -> list[tuple[str, object, str]]:
    """Read explicit labels without depending on a model selecting the correct line."""
    candidates: list[tuple[str, object, str]] = []
    for name, field in fields.items():
        if field.field_type is MetadataFieldType.OBJECT_LIST:
            continue
        aliases = {field.label, name.replace("_", " ")}
        for patterns in FIELD_PATTERNS.values():
            aliases.update(patterns.get(name, ()))
        alternatives = "|".join(
            re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)
        )
        pattern = r"^[ \t]*(?:" + alternatives + r")[ ]*(?::|#|\t| {2,}|\r?\n)[ \t]*[^\r\n]+"
        for match in re.finditer(pattern, source, flags=re.I | re.M):
            quote = match.group().strip()
            candidates.append((name, labelled_value(field, quote, None), quote))
    return candidates


def critical_line(text: str) -> bool:
    return bool(action_topics(text)) or bool(
        re.search(r"\b(?:no evidence of|must not)\b", text, re.I)
    )


def expand_line_payload(
    payload: dict[str, Any],
    page_number: int,
    window: str,
    lines: tuple[SourceLine, ...],
    fields: dict[str, MetadataFieldDefinition],
) -> dict[str, Any]:
    if isinstance(payload.get("quotes"), dict) or "extracted_metadata" in payload:
        return payload
    metadata, evidence, summaries, tags, withheld = {}, [], [], [], []
    raw_fields = payload.get("fields")
    if isinstance(raw_fields, dict):
        for name, item in raw_fields.items():
            if not isinstance(item, dict):
                continue
            quote = referenced_quote(item.get("lines"), lines, window)
            field = fields.get(name)
            if quote is None or field is None:
                withheld.append(str(name))
                continue
            value = labelled_value(field, quote, item.get("value"))
            if value is None or value == "":
                withheld.append(str(name))
                continue
            metadata[name] = value
            evidence.append({"field": name, "page_number": page_number, "quote": quote})
    summary = payload.get("summary", [])
    critical = payload.get("critical", [])
    selected = (
        list(critical) + list(summary)
        if isinstance(summary, list) and isinstance(critical, list)
        else []
    )
    for number in selected:
        quote = referenced_quote([number], lines, window)
        if quote is not None:
            summaries.append(
                {
                    "page_number": page_number,
                    "quote": quote,
                    "importance": 3 if number in critical else 2,
                }
            )
    raw_tags = payload.get("tags")
    if isinstance(raw_tags, dict):
        for name, references in raw_tags.items():
            quote = referenced_quote(references, lines, window)
            if quote:
                tags.append({"name": name, "page_number": page_number, "quote": quote})
    return {
        **payload,
        "extracted_metadata": metadata,
        "field_evidence": evidence,
        "summary_points": summaries,
        "tags": tags,
        "withheld_fields": withheld,
    }
