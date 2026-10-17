"""Explicit source contexts for typed facts, including narrative document wording."""

import re
from decimal import Decimal

from papervault_api.documents.domain.document_types import MetadataFieldDefinition
from papervault_api.documents.domain.metadata import parse_date
from papervault_api.documents.infrastructure.ai import FIELD_PATTERNS

CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "employer": ("employer", "company name", "legal employer"),
    "employee_name": ("employee name", "name of employee", "employee"),
    "position": ("position", "designation", "job title", "appointed as", "position of"),
    "start_date": (
        "start date",
        "date of joining",
        "joining date",
        "commencement date",
        "commence on",
        "commences on",
        "commence from",
        "effective from",
    ),
    "end_date": ("end date", "contract ends on", "employment ends on", "expire on", "expires on"),
    "annual_compensation": (
        "annual compensation",
        "annual salary",
        "annual remuneration",
        "annual ctc",
        "total ctc",
        "cost to company",
        "ctc",
    ),
    "expiry_date": ("date of expiry",),
    "issue_date": ("date of issue",),
}
DATE_TOKEN = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
    r"\d{1,2}(?:st|nd|rd|th)?(?:\s+|-)[A-Za-z]+(?:\s+|-)\d{4}|"
    r"[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b",
    re.I,
)
ENTITY_FIELDS = {
    "employer",
    "employee_name",
    "position",
    "provider",
    "patient_name",
    "taxpayer_name",
    "vendor",
    "bank",
    "issuer",
    "organization",
}


def field_aliases(field: MetadataFieldDefinition) -> tuple[str, ...]:
    aliases = {field.label, field.key.replace("_", " "), *CONTEXT_ALIASES.get(field.key, ())}
    for patterns in FIELD_PATTERNS.values():
        aliases.update(patterns.get(field.key, ()))
    return tuple(sorted(aliases, key=len, reverse=True))


def contextual_date(quote: str, field: MetadataFieldDefinition, locale: str) -> str | None:
    candidates = date_source_candidates(quote, field, locale)
    return candidates[0][0] if candidates else None


def date_source_candidates(
    source: str, field: MetadataFieldDefinition, locale: str
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for alias in field_aliases(field):
        for match in re.finditer(r"\b" + re.escape(alias) + r"\b", source, flags=re.I):
            tail = source[match.end() : match.end() + 220]
            date = DATE_TOKEN.search(tail)
            if date is None:
                continue
            # Bind only an explicit date with simple connecting words. A missing
            # start date must not borrow the date from the next end-date field.
            gap = tail[: date.start()]
            if not re.fullmatch(
                r"[\s:#=\u2013\u2014-]*(?:(?:is|shall be|will be|on|from|the)\s+)*", gap, re.I
            ):
                continue
            try:
                value = parse_date(date.group(), locale=locale)
            except ValueError:
                continue
            candidates.append((value, source[match.start() : match.end() + date.end()]))
    return candidates


def contextual_amount(quote: str, field: MetadataFieldDefinition) -> int | float | None:
    if field.key == "annual_compensation" and not re.search(
        r"\b(?:annual|annually|yearly|per annum|lpa)\b|\bp\.a\.", quote, flags=re.I
    ):
        return None
    for alias in field_aliases(field):
        match = re.search(r"\b" + re.escape(alias) + r"\b", quote, flags=re.I)
        if not match:
            continue
        tail = quote[match.end() :]
        number = re.search(
            r"([-+]?\d[\d,]*(?:\.\d+)?)\s*(lakh(?:s)?|lac(?:s)?|lpa|crore(?:s)?|million|thousand)?\b",
            tail,
            flags=re.I,
        )
        if number:
            prefix = tail[: number.start()]
            if re.search(
                r"\b(?:not specified|not stated|not provided|unspecified|unknown|n/a)\b|"
                r"\n[^\n:]{1,60}:|(?<!Rs)\.(?:\s|$)",
                prefix,
                re.I,
            ):
                return None
            if tail[number.end() :].lstrip().startswith("%"):
                return None
            amount = Decimal(number.group(1).replace(",", ""))
            if re.search(
                r"\(\s*(?:(?:INR|Rs\.?|USD|EUR|[$₹€])\s*)?$", tail[: number.start()], re.I
            ) and tail[number.end() :].lstrip().startswith(")"):
                amount = -abs(amount)
            unit = (number.group(2) or "").casefold()
            multiplier = (
                100000
                if unit.startswith(("lakh", "lac")) or unit == "lpa"
                else 10000000
                if unit.startswith("crore")
                else 1000000
                if unit == "million"
                else 1000
                if unit == "thousand"
                else 1
            )
            result = amount * multiplier
            return int(result) if result == result.to_integral_value() else float(round(result, 2))
    return None


def equivalent_values(field: str, first: object, second: object) -> bool:
    if field in ENTITY_FIELDS and isinstance(first, str) and isinstance(second, str):
        return " ".join(first.casefold().split()) == " ".join(second.casefold().split())
    return first == second


def bound_party_role(quote: str, value: str) -> str | None:
    """Recognize explicit party definitions without guessing from an entity's proximity."""
    match = re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote, re.I)
    if match is None:
        return None
    before, after = quote[: match.start()], quote[match.end() :]
    suffix = re.match(
        r"\s*(?:\([^)]{0,50}\)\s*)?(?:is\s+the\s+)?"
        r"\([^)]{0,100}\b(employer|employee|company)\b[^)]*\)",
        after,
        re.I,
    )
    if suffix is None:
        suffix = re.match(r"\s+is\s+the\s+(employer|employee)\b", after, re.I)
    prefix = re.search(r"\b(employer|employee)(?:\s+name)?\s*(?::|is)\s*$", before, re.I)
    role = suffix.group(1) if suffix else prefix.group(1) if prefix else None
    return (
        "employer" if role and role.casefold() == "company" else role.casefold() if role else None
    )
