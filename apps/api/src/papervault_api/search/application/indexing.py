import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextExtraction,
)
from papervault_api.tags.infrastructure.models import DocumentTag, Tag


@dataclass(frozen=True, slots=True)
class SearchIndexDocument:
    document_id: UUID
    owner_id: UUID
    title: str
    original_filename: str
    content_type: str
    status: str
    document_type: str
    created_at: datetime
    updated_at: datetime
    document_date: date | None = None
    issuer: str | None = None
    organization: str | None = None
    summary: str | None = None
    text: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    keywords: tuple[str, ...] = ()
    suggested_tags: tuple[str, ...] = ()
    entities: tuple[dict[str, Any], ...] = ()
    embedding: tuple[float, ...] | None = None
    embedding_dimensions: int | None = None
    source_text_sha256: str | None = None


class SearchDocumentIndex(Protocol):
    def ensure_index(self) -> None:
        raise NotImplementedError

    def index_document(self, document: SearchIndexDocument) -> None:
        raise NotImplementedError

    def delete_document(self, document_id: UUID) -> None:
        raise NotImplementedError


class SearchIndexingService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        search_index: SearchDocumentIndex,
    ) -> None:
        self._session = session
        self._search_index = search_index

    async def index_document(self, document_id: UUID) -> bool:
        projection = await self._build_document_projection(document_id)
        if projection is None:
            await asyncio.to_thread(self._search_index.delete_document, document_id)
            return False

        await asyncio.to_thread(self._search_index.ensure_index)
        await asyncio.to_thread(self._search_index.index_document, projection)
        return True

    async def index_owner_documents(self, owner_id: UUID, *, limit: int = 500) -> int:
        result = await self._session.execute(
            select(Document.id)
            .where(Document.owner_id == owner_id)
            .order_by(Document.updated_at.desc())
            .limit(limit),
        )
        document_ids = list(result.scalars())
        if not document_ids:
            return 0

        await asyncio.to_thread(self._search_index.ensure_index)
        indexed_count = 0
        for document_id in document_ids:
            projection = await self._build_document_projection(document_id)
            if projection is None:
                continue
            await asyncio.to_thread(self._search_index.index_document, projection)
            indexed_count += 1
        return indexed_count

    async def _build_document_projection(self, document_id: UUID) -> SearchIndexDocument | None:
        document = await self._session.get(Document, document_id)
        if document is None:
            return None

        text_extraction = await self._load_current_text_extraction(document_id)
        embedding = await self._load_current_embedding(document_id)
        ai_analysis = await self._load_current_ai_analysis(document_id)
        metadata = await self._load_current_metadata(document_id)
        tags = await self._load_tags(document_id)

        return SearchIndexDocument(
            document_id=document.id,
            owner_id=document.owner_id,
            title=document.title,
            original_filename=document.original_filename,
            content_type=document.content_type,
            status=document.status,
            document_type=document.document_type,
            document_date=document.document_date,
            issuer=document.issuer,
            organization=document.organization,
            summary=document.summary,
            created_at=document.created_at,
            updated_at=document.updated_at,
            text=text_extraction.content_text if text_extraction is not None else None,
            tags=tags,
            metadata=metadata.data if metadata is not None else {},
            keywords=tuple(ai_analysis.keywords) if ai_analysis is not None else (),
            suggested_tags=(tuple(ai_analysis.suggested_tags) if ai_analysis is not None else ()),
            entities=tuple(ai_analysis.entities) if ai_analysis is not None else (),
            embedding=tuple(float(value) for value in embedding.vector)
            if embedding is not None
            else None,
            embedding_dimensions=embedding.dimensions if embedding is not None else None,
            source_text_sha256=embedding.source_text_sha256 if embedding is not None else None,
        )

    async def _load_current_text_extraction(
        self,
        document_id: UUID,
    ) -> DocumentTextExtraction | None:
        result = await self._session.execute(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _load_current_embedding(self, document_id: UUID) -> DocumentEmbedding | None:
        result = await self._session.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.document_id == document_id,
                DocumentEmbedding.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _load_current_ai_analysis(self, document_id: UUID) -> DocumentAIAnalysis | None:
        result = await self._session.execute(
            select(DocumentAIAnalysis).where(
                DocumentAIAnalysis.document_id == document_id,
                DocumentAIAnalysis.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _load_current_metadata(self, document_id: UUID) -> DocumentMetadataRecord | None:
        result = await self._session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document_id,
                DocumentMetadataRecord.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _load_tags(self, document_id: UUID) -> tuple[str, ...]:
        result = await self._session.execute(
            select(Tag.slug)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document_id)
            .order_by(Tag.slug),
        )
        return tuple(result.scalars())


class NullSearchDocumentIndex:
    def ensure_index(self) -> None:
        return None

    def index_document(self, document: SearchIndexDocument) -> None:
        return None

    def delete_document(self, document_id: UUID) -> None:
        return None
