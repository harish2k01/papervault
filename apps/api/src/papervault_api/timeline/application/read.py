from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import Document
from papervault_api.timeline.infrastructure.models import TimelineEvent


@dataclass(frozen=True, slots=True)
class VaultTimelineItem:
    id: UUID
    document_id: UUID | None
    document_title: str | None
    event_type: str
    payload: dict[str, object]
    occurred_at: datetime


class VaultTimelineReadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_events(
        self,
        *,
        owner_id: UUID,
        limit: int,
        offset: int,
        event_type: str | None = None,
        document_id: UUID | None = None,
    ) -> tuple[VaultTimelineItem, ...]:
        statement = (
            select(TimelineEvent, Document.title)
            .outerjoin(Document, Document.id == TimelineEvent.document_id)
            .where(TimelineEvent.owner_id == owner_id)
        )
        if event_type:
            statement = statement.where(TimelineEvent.event_type == event_type)
        if document_id:
            statement = statement.where(TimelineEvent.document_id == document_id)
        result = await self._session.execute(
            statement.order_by(TimelineEvent.occurred_at.desc()).offset(offset).limit(limit)
        )
        return tuple(
            VaultTimelineItem(
                id=event.id,
                document_id=event.document_id,
                document_title=document_title,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for event, document_title in result.all()
        )
