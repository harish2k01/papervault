from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.domain.enums import DocumentReviewStatus, DocumentStatus
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentMetadataRecord,
    DocumentTextBlock,
    DocumentTextExtraction,
    DocumentVersion,
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
class DocumentVersionView:
    id: UUID
    version_number: int
    original_filename: str
    content_type: str
    sha256_hash: str
    file_size_bytes: int
    change_reason: str | None
    is_current: bool
    created_by_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    document: Document
    current_ai_analysis: DocumentAIAnalysis | None
    current_metadata: DocumentMetadataRecord | None
    current_text_extraction: DocumentTextExtraction | None
    tags: tuple[DocumentTagView, ...]
    timeline_events: tuple[DocumentTimelineEventView, ...]
    versions: tuple[DocumentVersionView, ...]


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
            versions=await self._get_versions(document.id),
        )

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[Document, ...]:
        statement = select(Document).where(Document.owner_id == owner_id)
        if not include_archived:
            statement = statement.where(Document.status != DocumentStatus.ARCHIVED.value)
        result = await self._session.execute(
            statement.order_by(Document.created_at.desc()).offset(offset).limit(limit),
        )
        return tuple(result.scalars())

    async def get_document_file(self, *, document_id: UUID, owner_id: UUID) -> Document | None:
        return await self._get_document(document_id=document_id, owner_id=owner_id)

    async def list_review_queue(
        self,
        *,
        owner_id: UUID,
        limit: int = 100,
    ) -> tuple[Document, ...]:
        result = await self._session.execute(
            select(Document)
            .where(
                Document.owner_id == owner_id,
                Document.review_status == DocumentReviewStatus.PENDING.value,
                Document.status != DocumentStatus.ARCHIVED.value,
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
        return tuple(result.scalars())

    async def list_ocr_blocks(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        page_number: int,
        query: str | None = None,
    ) -> tuple[DocumentTextBlock, ...] | None:
        document = await self._get_document(document_id=document_id, owner_id=owner_id)
        if document is None:
            return None
        result = await self._session.execute(
            select(DocumentTextBlock)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.id == DocumentTextBlock.text_extraction_id,
            )
            .where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextBlock.page_number == page_number,
            )
            .order_by(DocumentTextBlock.block_index)
            .limit(2000)
        )
        blocks = tuple(result.scalars())
        terms = {term.casefold() for term in (query or "").split() if len(term) >= 2}
        if not terms:
            return blocks
        return tuple(
            block for block in blocks if any(term in block.text.casefold() for term in terms)
        )

    async def get_duplicate_candidates(self, owner_id: UUID) -> tuple[tuple[Document, ...], ...]:
        duplicate_hashes = (
            await self._session.execute(
                select(Document.sha256_hash)
                .where(
                    Document.owner_id == owner_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                )
                .group_by(Document.sha256_hash)
                .having(func.count(Document.id) > 1),
            )
        ).scalars()

        groups: list[tuple[Document, ...]] = []
        for sha256_hash in duplicate_hashes:
            documents = (
                await self._session.execute(
                    select(Document)
                    .where(
                        Document.owner_id == owner_id,
                        Document.sha256_hash == sha256_hash,
                        Document.status != DocumentStatus.ARCHIVED.value,
                    )
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

    async def _get_versions(self, document_id: UUID) -> tuple[DocumentVersionView, ...]:
        result = await self._session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc()),
        )
        return tuple(
            DocumentVersionView(
                id=version.id,
                version_number=version.version_number,
                original_filename=version.original_filename,
                content_type=version.content_type,
                sha256_hash=version.sha256_hash,
                file_size_bytes=version.file_size_bytes,
                change_reason=version.change_reason,
                is_current=version.is_current,
                created_by_id=version.created_by_id,
                created_at=version.created_at,
            )
            for version in result.scalars()
        )
