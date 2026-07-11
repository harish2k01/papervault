import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from papervault_api.documents.domain.document_types import (
    MetadataFieldDefinition,
    MetadataFieldType,
    get_document_type,
)

WHITESPACE_PATTERN = re.compile(r"\s+")
NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True, slots=True)
class MetadataIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class MetadataNormalizationResult:
    data: dict[str, object]
    issues: tuple[MetadataIssue, ...]


def normalize_document_metadata(
    document_type: str,
    data: dict[str, Any],
    *,
    locale: str = "en-IN",
) -> MetadataNormalizationResult:
    definition = get_document_type(document_type)
    fields = {field.key: field for field in definition.metadata_fields}
    normalized: dict[str, object] = {}
    issues: list[MetadataIssue] = []

    for key, value in data.items():
        field = fields.get(key)
        if field is None:
            normalized[key] = normalize_unknown(value)
            continue
        try:
            normalized_value = normalize_field(field, value, locale=locale)
        except (TypeError, ValueError) as exc:
            issues.append(
                MetadataIssue(
                    code="invalid_value",
                    field=key,
                    message=str(exc),
                )
            )
            normalized[key] = normalize_unknown(value)
            continue
        if normalized_value is not None:
            normalized[key] = normalized_value

    for field in definition.metadata_fields:
        if field.required and is_blank(normalized.get(field.key)):
            issues.append(
                MetadataIssue(
                    code="missing_required",
                    field=field.key,
                    message=f"{field.label} is required",
                )
            )

    return MetadataNormalizationResult(data=normalized, issues=tuple(issues))


def normalize_field(
    field: MetadataFieldDefinition,
    value: Any,
    *,
    locale: str,
) -> object | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if field.field_type is MetadataFieldType.STRING:
        return normalize_string(value)
    if field.field_type is MetadataFieldType.CURRENCY:
        return parse_number(value)
    if field.field_type is MetadataFieldType.DECIMAL:
        return parse_number(value)
    if field.field_type is MetadataFieldType.INTEGER:
        return parse_integer(field.key, value)
    if field.field_type is MetadataFieldType.DATE:
        return parse_date(value, locale=locale)
    if field.field_type is MetadataFieldType.BOOLEAN:
        return parse_boolean(value)
    if field.field_type is MetadataFieldType.OBJECT_LIST:
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError(f"{field.label} must be a list of objects")
        return [
            {normalize_string(key): normalize_unknown(item) for key, item in row.items()}
            for row in value[:200]
        ]
    return normalize_unknown(value)


def normalize_string(value: Any) -> str:
    return WHITESPACE_PATTERN.sub(" ", str(value)).strip()[:2000]


def parse_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a number")
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = normalize_string(value)
        match = NUMBER_PATTERN.search(text)
        if match is None:
            raise ValueError(f"Could not parse number from {text!r}")
        number = float(match.group().replace(",", ""))
        if text.startswith("(") and text.endswith(")"):
            number = -number
    return int(number) if number.is_integer() else round(number, 2)


def parse_integer(field_key: str, value: Any) -> int:
    if field_key == "month" and isinstance(value, str):
        month = MONTHS.get(value.strip().lower())
        if month is not None:
            return month
    number = parse_number(value)
    integer = int(number)
    if float(number) != integer:
        raise ValueError(f"{field_key} must be a whole number")
    if field_key == "month" and not 1 <= integer <= 12:
        raise ValueError("Month must be between 1 and 12")
    if field_key == "year" and not 1900 <= integer <= 2200:
        raise ValueError("Year must be between 1900 and 2200")
    return integer


def parse_date(value: Any, *, locale: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = normalize_string(value)
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y"]
    if locale.lower().startswith("en-us"):
        formats.extend(["%m/%d/%Y", "%m-%d-%Y"])
    else:
        formats.extend(["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"])
    for date_format in formats:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date from {text!r}")


def parse_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = normalize_string(value).lower()
    if normalized in {"true", "yes", "y", "1"}:
        return True
    if normalized in {"false", "no", "n", "0"}:
        return False
    raise ValueError(f"Could not parse boolean from {value!r}")


def normalize_unknown(value: Any) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [normalize_unknown(item) for item in value[:200]]
    if isinstance(value, dict):
        return {
            normalize_string(key)[:120]: normalize_unknown(item)
            for key, item in list(value.items())[:200]
        }
    return normalize_string(value)


def is_blank(value: object | None) -> bool:
    return value is None or value == "" or value == [] or value == {}
