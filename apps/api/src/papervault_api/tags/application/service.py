from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.rules import apply_document_rule, matches_document
from papervault_api.documents.domain.document_types import get_document_type
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.domain.rules import DocumentRule
from papervault_api.documents.infrastructure.models import Document
from papervault_api.tags.domain.enums import TagSource
from papervault_api.tags.infrastructure.models import DocumentTag, SmartTagRule, Tag
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class TagConflictError(ValueError):
    pass


class InvalidSmartTagRuleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TagSummary:
    tag: Tag
    document_count: int
    smart_rule: DocumentRule | None
    last_evaluated_at: datetime | None


@dataclass(frozen=True, slots=True)
class SmartTagRefreshResult:
    evaluated: int
    matched: int
    attached: int
    detached: int
    evaluated_at: datetime
    changed_document_ids: tuple[UUID, ...]


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_tags(self, owner_id: UUID) -> tuple[Tag, ...]:
        result = await self._session.execute(
            select(Tag).where(Tag.owner_id == owner_id).order_by(Tag.name.asc()),
        )
        return tuple(result.scalars())

    async def list_tag_summaries(self, owner_id: UUID) -> tuple[TagSummary, ...]:
        tags = await self.list_tags(owner_id)
        if not tags:
            return ()
        tag_ids = [tag.id for tag in tags]
        counts = {
            tag_id: int(count)
            for tag_id, count in (
                await self._session.execute(
                    select(DocumentTag.tag_id, func.count(DocumentTag.document_id))
                    .join(Document, Document.id == DocumentTag.document_id)
                    .where(
                        DocumentTag.tag_id.in_(tag_ids),
                        Document.status != DocumentStatus.ARCHIVED.value,
                    )
                    .group_by(DocumentTag.tag_id),
                )
            ).all()
        }
        rules = {
            rule.tag_id: rule
            for rule in (
                await self._session.execute(
                    select(SmartTagRule).where(SmartTagRule.tag_id.in_(tag_ids)),
                )
            ).scalars()
        }
        return tuple(
            TagSummary(
                tag=tag,
                document_count=counts.get(tag.id, 0),
                smart_rule=(
                    DocumentRule.from_mapping(rules[tag.id].rule) if tag.id in rules else None
                ),
                last_evaluated_at=(rules[tag.id].last_evaluated_at if tag.id in rules else None),
            )
            for tag in tags
        )

    async def create_tag(
        self,
        *,
        owner_id: UUID,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> Tag:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Tag name cannot be empty")
        slug = slugify(normalized_name)
        await self._ensure_available_slug(owner_id, slug)
        tag = Tag(
            owner_id=owner_id,
            name=normalized_name,
            slug=slug,
            description=normalize_optional(description, 255),
            color=normalize_optional(color, 20),
            source=TagSource.MANUAL.value,
        )
        self._session.add(tag)
        await self._session.commit()
        await self._session.refresh(tag)
        return tag

    async def create_smart_tag(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        name: str,
        rule: DocumentRule,
        description: str | None = None,
        color: str | None = None,
    ) -> tuple[Tag, SmartTagRefreshResult]:
        validate_smart_tag_rule(rule)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Tag name cannot be empty")
        slug = slugify(normalized_name)
        await self._ensure_available_slug(owner_id, slug)
        tag = Tag(
            owner_id=owner_id,
            name=normalized_name,
            slug=slug,
            description=normalize_optional(description, 255),
            color=normalize_optional(color, 20),
            source=TagSource.SMART.value,
        )
        self._session.add(tag)
        await self._session.flush()
        smart_rule = SmartTagRule(tag_id=tag.id, rule=rule.as_dict())
        self._session.add(smart_rule)
        await self._session.flush()
        refresh = await self._refresh_rule(
            owner_id=owner_id,
            actor_id=actor_id,
            tag=tag,
            smart_rule=smart_rule,
            rule=rule,
        )
        await self._session.commit()
        await self._session.refresh(tag)
        return tag, refresh

    async def update_smart_tag_rule(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        tag_id: UUID,
        rule: DocumentRule,
    ) -> tuple[Tag, SmartTagRefreshResult] | None:
        validate_smart_tag_rule(rule)
        tag = await self._owned_tag(owner_id, tag_id)
        if tag is None or tag.source != TagSource.SMART.value:
            return None
        smart_rule = await self._session.get(SmartTagRule, tag_id)
        if smart_rule is None:
            return None
        smart_rule.rule = rule.as_dict()
        refresh = await self._refresh_rule(
            owner_id=owner_id,
            actor_id=actor_id,
            tag=tag,
            smart_rule=smart_rule,
            rule=rule,
        )
        await self._session.commit()
        await self._session.refresh(tag)
        return tag, refresh

    async def refresh_smart_tag(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        tag_id: UUID,
    ) -> SmartTagRefreshResult | None:
        tag = await self._owned_tag(owner_id, tag_id)
        if tag is None or tag.source != TagSource.SMART.value:
            return None
        smart_rule = await self._session.get(SmartTagRule, tag_id)
        if smart_rule is None:
            return None
        result = await self._refresh_rule(
            owner_id=owner_id,
            actor_id=actor_id,
            tag=tag,
            smart_rule=smart_rule,
            rule=DocumentRule.from_mapping(smart_rule.rule),
        )
        await self._session.commit()
        return result

    async def synchronize_document(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        actor_id: UUID | None,
    ) -> tuple[UUID, ...]:
        document = await self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            ),
        )
        if document is None:
            return ()
        smart_rules = tuple(
            (
                await self._session.execute(
                    select(Tag, SmartTagRule)
                    .join(SmartTagRule, SmartTagRule.tag_id == Tag.id)
                    .where(
                        Tag.owner_id == owner_id,
                        Tag.source == TagSource.SMART.value,
                    ),
                )
            ).all()
        )
        changed: list[UUID] = []
        for tag, stored_rule in smart_rules:
            rule = DocumentRule.from_mapping(stored_rule.rule)
            link = await self._session.get(
                DocumentTag,
                {"document_id": document.id, "tag_id": tag.id},
            )
            matches = matches_document(document, rule)
            if matches and link is None:
                self._session.add(
                    DocumentTag(
                        document_id=document.id,
                        tag_id=tag.id,
                        source=TagSource.SMART.value,
                        assigned_by_id=None,
                    ),
                )
                self._session.add(
                    smart_tag_event(
                        owner_id=owner_id,
                        actor_id=actor_id,
                        document_id=document.id,
                        tag=tag,
                        action="smart_tag_attached",
                    ),
                )
                changed.append(document.id)
            elif not matches and link is not None and link.source == TagSource.SMART.value:
                await self._session.delete(link)
                self._session.add(
                    smart_tag_event(
                        owner_id=owner_id,
                        actor_id=actor_id,
                        document_id=document.id,
                        tag=tag,
                        action="smart_tag_detached",
                    ),
                )
                changed.append(document.id)
        await self._session.commit()
        return tuple(dict.fromkeys(changed))

    async def delete_tag(
        self,
        *,
        owner_id: UUID,
        tag_id: UUID,
    ) -> tuple[UUID, ...] | None:
        tag = await self._owned_tag(owner_id, tag_id)
        if tag is None:
            return None
        document_ids = tuple(
            (
                await self._session.execute(
                    select(DocumentTag.document_id).where(DocumentTag.tag_id == tag_id),
                )
            ).scalars()
        )
        await self._session.delete(tag)
        await self._session.commit()
        return document_ids

    async def attach_tag(self, *, owner_id: UUID, document_id: UUID, tag_id: UUID) -> bool:
        document = await self._session.get(Document, document_id)
        tag = await self._session.get(Tag, tag_id)
        if (
            document is None
            or tag is None
            or document.owner_id != owner_id
            or tag.owner_id != owner_id
        ):
            return False

        existing = await self._session.get(
            DocumentTag, {"document_id": document_id, "tag_id": tag_id}
        )
        if existing is None:
            self._session.add(
                DocumentTag(
                    document_id=document_id,
                    tag_id=tag_id,
                    source=TagSource.MANUAL.value,
                    assigned_by_id=owner_id,
                ),
            )
            self._session.add(
                TimelineEvent(
                    owner_id=owner_id,
                    actor_id=owner_id,
                    document_id=document_id,
                    event_type=TimelineEventType.TAGS_CHANGED.value,
                    payload={"action": "attached", "tag": tag.slug},
                ),
            )
        elif existing.source != TagSource.MANUAL.value:
            existing.source = TagSource.MANUAL.value
            existing.assigned_by_id = owner_id
            existing.confidence_score = None
        await self._session.commit()
        return True

    async def detach_tag(self, *, owner_id: UUID, document_id: UUID, tag_id: UUID) -> bool:
        document = await self._session.get(Document, document_id)
        tag = await self._session.get(Tag, tag_id)
        if (
            document is None
            or tag is None
            or document.owner_id != owner_id
            or tag.owner_id != owner_id
        ):
            return False

        existing = await self._session.get(
            DocumentTag, {"document_id": document_id, "tag_id": tag_id}
        )
        if existing is not None:
            await self._session.delete(existing)
            self._session.add(
                TimelineEvent(
                    owner_id=owner_id,
                    actor_id=owner_id,
                    document_id=document_id,
                    event_type=TimelineEventType.TAGS_CHANGED.value,
                    payload={"action": "detached", "tag": tag.slug},
                ),
            )
        await self._session.commit()
        return True

    async def apply_automatic_tags(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        suggestions: tuple[str, ...],
        confidence_score: float,
    ) -> tuple[Tag, ...]:
        if confidence_score < 0.6:
            return ()

        normalized = tuple(
            dict.fromkeys(
                suggestion.strip()[:80] for suggestion in suggestions if suggestion.strip()
            )
        )[:5]
        if not normalized:
            return ()

        applied: list[Tag] = []
        for suggestion in normalized:
            slug = slugify(suggestion)
            tag = await self._session.scalar(
                select(Tag).where(Tag.owner_id == owner_id, Tag.slug == slug),
            )
            if tag is None:
                tag = Tag(
                    owner_id=owner_id,
                    name=display_name(suggestion),
                    slug=slug,
                    source=TagSource.AI.value,
                )
                self._session.add(tag)
                await self._session.flush()

            link = await self._session.get(
                DocumentTag,
                {"document_id": document_id, "tag_id": tag.id},
            )
            if link is None:
                self._session.add(
                    DocumentTag(
                        document_id=document_id,
                        tag_id=tag.id,
                        source=TagSource.AI.value,
                        confidence_score=Decimal(str(confidence_score)),
                    ),
                )
                applied.append(tag)
            elif link.source == TagSource.AI.value:
                link.confidence_score = Decimal(str(confidence_score))

        if applied:
            self._session.add(
                TimelineEvent(
                    owner_id=owner_id,
                    actor_id=None,
                    document_id=document_id,
                    event_type=TimelineEventType.TAGS_CHANGED.value,
                    payload={
                        "action": "automatic_tags_applied",
                        "tags": [tag.slug for tag in applied],
                        "confidence_score": confidence_score,
                    },
                ),
            )
        return tuple(applied)

    async def _refresh_rule(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        tag: Tag,
        smart_rule: SmartTagRule,
        rule: DocumentRule,
    ) -> SmartTagRefreshResult:
        document_ids = set(
            (
                await self._session.execute(
                    select(Document.id).where(Document.owner_id == owner_id),
                )
            ).scalars()
        )
        matching_ids = set(
            (
                await self._session.execute(
                    apply_document_rule(
                        select(Document.id).where(Document.owner_id == owner_id),
                        rule,
                    ),
                )
            ).scalars()
        )
        existing_links = {
            link.document_id: link
            for link in (
                await self._session.execute(
                    select(DocumentTag).where(DocumentTag.tag_id == tag.id),
                )
            ).scalars()
        }

        attached = 0
        detached = 0
        changed: list[UUID] = []
        for document_id in matching_ids:
            if document_id in existing_links:
                continue
            self._session.add(
                DocumentTag(
                    document_id=document_id,
                    tag_id=tag.id,
                    source=TagSource.SMART.value,
                    assigned_by_id=None,
                ),
            )
            self._session.add(
                smart_tag_event(
                    owner_id=owner_id,
                    actor_id=actor_id,
                    document_id=document_id,
                    tag=tag,
                    action="smart_tag_attached",
                ),
            )
            attached += 1
            changed.append(document_id)

        for document_id, link in existing_links.items():
            if document_id in matching_ids or link.source != TagSource.SMART.value:
                continue
            await self._session.delete(link)
            self._session.add(
                smart_tag_event(
                    owner_id=owner_id,
                    actor_id=actor_id,
                    document_id=document_id,
                    tag=tag,
                    action="smart_tag_detached",
                ),
            )
            detached += 1
            changed.append(document_id)

        evaluated_at = datetime.now(UTC)
        smart_rule.last_evaluated_at = evaluated_at
        return SmartTagRefreshResult(
            evaluated=len(document_ids),
            matched=len(matching_ids),
            attached=attached,
            detached=detached,
            evaluated_at=evaluated_at,
            changed_document_ids=tuple(dict.fromkeys(changed)),
        )

    async def _owned_tag(self, owner_id: UUID, tag_id: UUID) -> Tag | None:
        result = await self._session.execute(
            select(Tag).where(Tag.id == tag_id, Tag.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def _ensure_available_slug(self, owner_id: UUID, slug: str) -> None:
        existing = await self._session.scalar(
            select(Tag.id).where(Tag.owner_id == owner_id, Tag.slug == slug),
        )
        if existing is not None:
            raise TagConflictError("A tag with this name already exists")


def validate_smart_tag_rule(rule: DocumentRule) -> None:
    if rule.is_empty:
        raise InvalidSmartTagRuleError("Smart tags require at least one matching condition")
    if rule.tags_any:
        raise InvalidSmartTagRuleError("Smart tag rules cannot depend on other tags")
    if rule.include_archived:
        raise InvalidSmartTagRuleError("Smart tags cannot include archived documents")
    for document_type in rule.document_types:
        get_document_type(document_type)


def smart_tag_event(
    *,
    owner_id: UUID,
    actor_id: UUID | None,
    document_id: UUID,
    tag: Tag,
    action: str,
) -> TimelineEvent:
    return TimelineEvent(
        owner_id=owner_id,
        actor_id=actor_id,
        document_id=document_id,
        event_type=TimelineEventType.TAGS_CHANGED.value,
        payload={
            "action": action,
            "tag": tag.slug,
            "tag_id": str(tag.id),
        },
    )


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "tag"


def display_name(value: str) -> str:
    return " ".join(part.capitalize() for part in SLUG_PATTERN.split(value) if part)[:80]


def normalize_optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized[:max_length] or None
