from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class InvalidDocumentRuleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentRule:
    document_types: tuple[str, ...] = ()
    title_contains: str | None = None
    issuer_contains: str | None = None
    organization_contains: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    tags_any: tuple[str, ...] = ()
    include_archived: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> DocumentRule:
        data = value or {}
        rule = cls(
            document_types=normalize_list(data.get("document_types"), max_items=20),
            title_contains=normalize_text(data.get("title_contains"), max_length=120),
            issuer_contains=normalize_text(data.get("issuer_contains"), max_length=120),
            organization_contains=normalize_text(
                data.get("organization_contains"),
                max_length=120,
            ),
            date_from=parse_date(data.get("date_from")),
            date_to=parse_date(data.get("date_to")),
            tags_any=tuple(
                slugify_rule_value(item)
                for item in normalize_list(data.get("tags_any"), max_items=20)
            ),
            include_archived=bool(data.get("include_archived", False)),
        )
        if rule.date_from and rule.date_to and rule.date_from > rule.date_to:
            raise InvalidDocumentRuleError("date_from cannot be after date_to")
        return rule

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_types": list(self.document_types),
            "title_contains": self.title_contains,
            "issuer_contains": self.issuer_contains,
            "organization_contains": self.organization_contains,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "tags_any": list(self.tags_any),
            "include_archived": self.include_archived,
        }

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.document_types,
                self.title_contains,
                self.issuer_contains,
                self.organization_contains,
                self.date_from,
                self.date_to,
                self.tags_any,
            )
        )


def normalize_list(value: Any, *, max_items: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise InvalidDocumentRuleError("Rule list values must be arrays")
    normalized = tuple(
        dict.fromkeys(
            item.strip()[:120] for item in value if isinstance(item, str) and item.strip()
        )
    )
    if len(normalized) > max_items:
        raise InvalidDocumentRuleError(f"Rule lists cannot contain more than {max_items} values")
    return normalized


def normalize_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidDocumentRuleError("Rule text values must be strings")
    normalized = value.strip()
    return normalized[:max_length] or None


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise InvalidDocumentRuleError("Rule dates must use ISO format") from exc
    raise InvalidDocumentRuleError("Rule dates must use ISO format")


def slugify_rule_value(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "tag"
