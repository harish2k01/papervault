from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentMetadataRecord,
    DocumentTextExtraction,
)
from papervault_api.tags.infrastructure.models import DocumentTag, Tag
from papervault_api.timeline.infrastructure.models import TimelineEvent


@dataclass(frozen=True, slots=True)
class DocumentTagView:
    id: UUID
    name: str
    slug: str
    color: str | None


@dataclass(frozen=True, slots=True)
class DocumentTimelineEventView:
    id: UUID
    event_type: str
    payload: dict[str, object]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    document: Document
    current_ai_analysis: DocumentAIAnalysis | None
    current_metadata: DocumentMetadataRecord | None
    current_text_extraction: DocumentTextExtraction | None
    tags: tuple[DocumentTagView, ...]
    timeline_events: tuple[DocumentTimelineEventView, ...]


class DocumentReadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_detail(self, *, document_id: UUID, owner_id: UUID) -> DocumentDetail | None:
        document = await self._get_document(document_id=document_id, owner_id=owner_id)
        if document is None:
            return None
        return DocumentDetail(
            document=document,
            current_ai_analysis=await self._get_current_ai_analysis(document.id),
            current_metadata=await self._get_current_metadata(document.id),
            current_text_extraction=await self._get_current_text_extraction(document.id),
            tags=await self._get_tags(document.id),
            timeline_events=await self._get_timeline(document.id),
        )

    async def list_documents(
        self, *, owner_id: UUID, limit: int = 50, offset: int = 0
    ) -> tuple[Document, ...]:
        result = await self._session.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit),
        )
        return tuple(result.scalars())

    async def get_document_file(self, *, document_id: UUID, owner_id: UUID) -> Document | None:
        return await self._get_document(document_id=document_id, owner_id=owner_id)

    async def get_duplicate_candidates(self, owner_id: UUID) -> tuple[tuple[Document, ...], ...]:
        duplicate_hashes = (
            await self._session.execute(
                select(Document.sha256_hash)
                .where(Document.owner_id == owner_id)
                .group_by(Document.sha256_hash)
                .having(func.count(Document.id) > 1),
            )
        ).scalars()

        groups: list[tuple[Document, ...]] = []
        for sha256_hash in duplicate_hashes:
            documents = (
                await self._session.execute(
                    select(Document)
                    .where(Document.owner_id == owner_id, Document.sha256_hash == sha256_hash)
                    .order_by(Document.created_at.asc()),
                )
            ).scalars()
            groups.append(tuple(documents))
        return tuple(groups)

    async def _get_document(self, *, document_id: UUID, owner_id: UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id),
        )
        return result.scalar_one_or_none()

    async def _get_current_ai_analysis(self, document_id: UUID) -> DocumentAIAnalysis | None:
        result = await self._session.execute(
            select(DocumentAIAnalysis).where(
                DocumentAIAnalysis.document_id == document_id,
                DocumentAIAnalysis.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _get_current_metadata(self, document_id: UUID) -> DocumentMetadataRecord | None:
        result = await self._session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document_id,
                DocumentMetadataRecord.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _get_current_text_extraction(
        self, document_id: UUID
    ) -> DocumentTextExtraction | None:
        result = await self._session.execute(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _get_tags(self, document_id: UUID) -> tuple[DocumentTagView, ...]:
        result = await self._session.execute(
            select(Tag)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document_id)
            .order_by(Tag.name.asc()),
        )
        return tuple(
            DocumentTagView(
                id=tag.id,
                name=tag.name,
                slug=tag.slug,
                color=tag.color,
            )
            for tag in result.scalars()
        )

    async def _get_timeline(self, document_id: UUID) -> tuple[DocumentTimelineEventView, ...]:
        result = await self._session.execute(
            select(TimelineEvent)
            .where(TimelineEvent.document_id == document_id)
            .order_by(TimelineEvent.occurred_at.desc()),
        )
        return tuple(
            DocumentTimelineEventView(
                id=event.id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for event in result.scalars()
        )
