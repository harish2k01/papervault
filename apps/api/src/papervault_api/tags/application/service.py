import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import Document
from papervault_api.tags.domain.enums import TagSource
from papervault_api.tags.infrastructure.models import DocumentTag, Tag
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_tags(self, owner_id: UUID) -> tuple[Tag, ...]:
        result = await self._session.execute(
            select(Tag).where(Tag.owner_id == owner_id).order_by(Tag.name.asc()),
        )
        return tuple(result.scalars())

    async def create_tag(
        self,
        *,
        owner_id: UUID,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> Tag:
        tag = Tag(
            owner_id=owner_id,
            name=name.strip(),
            slug=slugify(name),
            description=description,
            color=color,
            source=TagSource.MANUAL.value,
        )
        self._session.add(tag)
        await self._session.commit()
        await self._session.refresh(tag)
        return tag

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


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "tag"
