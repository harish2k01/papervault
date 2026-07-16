from __future__ import annotations

from typing import Any

from sqlalchemy import Select, exists, func, select

from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.domain.rules import DocumentRule
from papervault_api.documents.infrastructure.models import Document
from papervault_api.tags.infrastructure.models import DocumentTag, Tag


def apply_document_rule(statement: Select[Any], rule: DocumentRule) -> Select[Any]:
    if not rule.include_archived:
        statement = statement.where(Document.status != "archived")
    if rule.document_types:
        statement = statement.where(Document.document_type.in_(rule.document_types))
    if rule.title_contains:
        statement = statement.where(case_insensitive_contains(Document.title, rule.title_contains))
    if rule.issuer_contains:
        statement = statement.where(
            case_insensitive_contains(Document.issuer, rule.issuer_contains)
        )
    if rule.organization_contains:
        statement = statement.where(
            case_insensitive_contains(Document.organization, rule.organization_contains)
        )
    if rule.date_from:
        statement = statement.where(Document.document_date >= rule.date_from)
    if rule.date_to:
        statement = statement.where(Document.document_date <= rule.date_to)
    if rule.tags_any:
        statement = statement.where(
            exists(
                select(DocumentTag.document_id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(
                    DocumentTag.document_id == Document.id,
                    Tag.slug.in_(rule.tags_any),
                )
            )
        )
    return statement


def matches_document(document: Document, rule: DocumentRule) -> bool:
    if not rule.include_archived and document.status == DocumentStatus.ARCHIVED.value:
        return False
    if rule.document_types and document.document_type not in rule.document_types:
        return False
    if rule.title_contains and not contains(document.title, rule.title_contains):
        return False
    if rule.issuer_contains and not contains(document.issuer, rule.issuer_contains):
        return False
    if rule.organization_contains and not contains(
        document.organization,
        rule.organization_contains,
    ):
        return False
    if rule.date_from and (
        document.document_date is None or document.document_date < rule.date_from
    ):
        return False
    return not (
        rule.date_to
        and (document.document_date is None or document.document_date > rule.date_to)
    )


def case_insensitive_contains(column: Any, value: str) -> Any:
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(column).like(f"%{escaped}%", escape="\\")


def contains(value: str | None, expected: str) -> bool:
    return expected.casefold() in (value or "").casefold()
