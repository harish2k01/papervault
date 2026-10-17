"""Source references and typed values that do not depend on generated quote text."""

import json
import re
from dataclasses import dataclass
from typing import Any

from papervault_api.documents.domain.document_types import (
    MetadataFieldDefinition,
    MetadataFieldType,
)
from papervault_api.documents.infrastructure.field_context import contextual_amount, field_aliases


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


def labelled_value(
    field: MetadataFieldDefinition,
    quote: str,
    suggested: object,
    fields: dict[str, MetadataFieldDefinition] | None = None,
) -> object:
    boundary = "|".join(
        re.escape(alias)
        for definition in (fields or {}).values()
        for alias in field_aliases(definition)
    )
    next_label = r"\s+(?:" + boundary + r")\s*[:#\t]" if boundary else None
    if field.field_type in {MetadataFieldType.CURRENCY, MetadataFieldType.DECIMAL}:
        amount = contextual_amount(quote, field)
        return amount if amount is not None else suggested
    if (
        field.field_type is MetadataFieldType.STRING
        and isinstance(suggested, str)
        and suggested
        and re.search(r"(?<!\w)" + re.escape(suggested) + r"(?!\w)", quote, flags=re.I)
        and (next_label is None or re.search(next_label, suggested, re.I) is None)
    ):
        return suggested
    for alias in field_aliases(field):
        match = re.search(r"\b" + re.escape(alias) + r"\b", quote, flags=re.I)
        if not match:
            continue
        tail = quote[match.end() :].lstrip(" \t\r\n:#")
        if tail.startswith(("- ", "\u2013 ", "\u2014 ")):
            tail = tail[2:]
        first_line = tail.splitlines()[0] if tail else ""
        if next_label:
            first_line = re.split(next_label, first_line, maxsplit=1, flags=re.I)[0]
        if field.field_type is MetadataFieldType.STRING:
            # A role mentioned in legal prose is not a label/value record.
            if not re.search(r"(?<!\w)" + re.escape(alias) + r"\s*(?::|#|\t|\n)", quote, re.I):
                continue
            first_line = re.split(
                r"\s*\(\s*(?:hereinafter|referred|defined)\b", first_line, maxsplit=1, flags=re.I
            )[0]
            if re.match(
                r"[\s\"']*(?:means|shall mean|includes|the company|the employee)\b",
                first_line,
                re.I,
            ):
                return None
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
        alternatives = "|".join(re.escape(alias) for alias in field_aliases(field))
        pattern = (
            r"(?=((?<!\w)(?:" + alternatives + r")[ ]*[:#][ \t]*[^\r\n]+|"
            r"^[ \t]*(?:" + alternatives + r")[ ]*(?:\t| {2,}|\r?\n)[ \t]*[^\r\n]+))"
        )
        for match in re.finditer(pattern, source, flags=re.I | re.M):
            quote = match.group(1).strip()
            candidates.append((name, labelled_value(field, quote, None, fields), quote))
        if name == "position":
            # An explicit appointment clause binds the title even when a small model
            # selects its sentence but omits or invents the structured value.
            appointment = (
                r"\b(?:you (?:are|will be|have been)|(?:the )?employee (?:is|will be))"
                r"\s+appointed\s+as\s+([^.;\r\n]{2,120})(?=[.;\r\n]|$)"
            )
            for match in re.finditer(appointment, source, re.I):
                prefix = source[max(0, match.start() - 60) : match.start()]
                if re.search(r"\b(?:if|unless|when|not)\b[^.\r\n]*$", prefix, re.I):
                    continue
                candidates.append((name, match.group(1).strip(), match.group()))
    return candidates


def critical_line(text: str) -> bool:
    return bool(action_topics(text)) or bool(
        re.search(r"\b(?:no evidence of|must|shall)\b", text, re.I)
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
            value = labelled_value(field, quote, item.get("value"), fields)
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
