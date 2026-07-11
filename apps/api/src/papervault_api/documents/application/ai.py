import hashlib
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.chunking import chunk_page_text
from papervault_api.documents.domain.enums import (
    AIAnalysisStatus,
    MetadataSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextChunk,
    DocumentTextExtraction,
    DocumentTextPage,
)


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    kind: str
    value: str
    confidence_score: float | None = None


@dataclass(frozen=True, slots=True)
class DocumentAIAnalysisResult:
    provider: str
    model: str
    summary: str
    keywords: tuple[str, ...]
    entities: tuple[ExtractedEntity, ...]
    suggested_tags: tuple[str, ...]
    category: str
    confidence_score: float
    extracted_metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    provider: str
    model: str
    dimensions: int
    vector: tuple[float, ...]
    vector_norm: float


class DocumentAIProvider(Protocol):
    def analyze(self, text: str, current_document_type: str) -> DocumentAIAnalysisResult:
        raise NotImplementedError


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> EmbeddingResult:
        raise NotImplementedError


class DocumentAIProcessingService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        ai_provider: DocumentAIProvider,
        embedding_provider: EmbeddingProvider,
        classification_threshold: float,
    ) -> None:
        self._session = session
        self._ai_provider = ai_provider
        self._embedding_provider = embedding_provider
        self._classification_threshold = classification_threshold

    async def process_document(self, document_id: UUID) -> None:
        document = await self._session.get(Document, document_id)
        if document is None:
            return

        text_extraction = await self._get_current_successful_text_extraction(document_id)
        if text_extraction is None or not text_extraction.content_text:
            return

        analysis = self._ai_provider.analyze(
            text_extraction.content_text,
            document.document_type,
        )
        embedding = self._embedding_provider.embed(text_extraction.content_text)
        text_hash = hashlib.sha256(text_extraction.content_text.encode("utf-8")).hexdigest()

        await self._mark_existing_ai_outputs_not_current(document_id)
        self._session.add(
            DocumentAIAnalysis(
                document_id=document_id,
                text_extraction_id=text_extraction.id,
                provider=analysis.provider,
                model=analysis.model,
                status=AIAnalysisStatus.SUCCEEDED.value,
                summary=analysis.summary,
                keywords=list(analysis.keywords),
                entities=[asdict(entity) for entity in analysis.entities],
                suggested_tags=list(analysis.suggested_tags),
                category=analysis.category,
                confidence_score=analysis.confidence_score,
                extracted_metadata=analysis.extracted_metadata,
                is_current=True,
            ),
        )
        self._session.add(
            DocumentEmbedding(
                document_id=document_id,
                text_extraction_id=text_extraction.id,
                provider=embedding.provider,
                model=embedding.model,
                dimensions=embedding.dimensions,
                vector=list(embedding.vector),
                vector_norm=embedding.vector_norm,
                source_text_sha256=text_hash,
                is_current=True,
            ),
        )
        await self._replace_text_chunks(document_id, text_extraction.id)

        if analysis.extracted_metadata:
            self._session.add(
                DocumentMetadataRecord(
                    document_id=document_id,
                    schema_name=analysis.category,
                    schema_version=1,
                    data=analysis.extracted_metadata,
                    source=MetadataSource.AI.value,
                    confidence_score=analysis.confidence_score,
                    extractor=f"{analysis.provider}:{analysis.model}",
                    is_current=True,
                ),
            )

        document.summary = analysis.summary
        if analysis.confidence_score >= self._classification_threshold:
            document.document_type = analysis.category

        await self._session.commit()

    async def _replace_text_chunks(
        self,
        document_id: UUID,
        text_extraction_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(DocumentTextChunk).where(
                DocumentTextChunk.text_extraction_id == text_extraction_id,
            )
        )
        result = await self._session.execute(
            select(DocumentTextPage)
            .where(DocumentTextPage.text_extraction_id == text_extraction_id)
            .order_by(DocumentTextPage.page_number)
        )
        for page in result.scalars():
            for chunk in chunk_page_text(page.page_number, page.content_text):
                embedding = self._embedding_provider.embed(chunk.content_text)
                self._session.add(
                    DocumentTextChunk(
                        document_id=document_id,
                        text_extraction_id=text_extraction_id,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        content_text=chunk.content_text,
                        token_count=chunk.token_count,
                        provider=embedding.provider,
                        model=embedding.model,
                        dimensions=embedding.dimensions,
                        vector=list(embedding.vector),
                        vector_norm=embedding.vector_norm,
                        source_text_sha256=hashlib.sha256(
                            chunk.content_text.encode("utf-8")
                        ).hexdigest(),
                    )
                )

    async def _get_current_successful_text_extraction(
        self,
        document_id: UUID,
    ) -> DocumentTextExtraction | None:
        result = await self._session.execute(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == TextExtractionStatus.SUCCEEDED.value,
            ),
        )
        return result.scalar_one_or_none()

    async def _mark_existing_ai_outputs_not_current(self, document_id: UUID) -> None:
        for analysis in await self._get_current_ai_analyses(document_id):
            analysis.is_current = False
        for embedding in await self._get_current_embeddings(document_id):
            embedding.is_current = False
        for metadata in await self._get_current_ai_metadata(document_id):
            metadata.is_current = False

    async def _get_current_ai_analyses(self, document_id: UUID) -> list[DocumentAIAnalysis]:
        result = await self._session.execute(
            select(DocumentAIAnalysis).where(
                DocumentAIAnalysis.document_id == document_id,
                DocumentAIAnalysis.is_current.is_(True),
            ),
        )
        return list(result.scalars())

    async def _get_current_embeddings(self, document_id: UUID) -> list[DocumentEmbedding]:
        result = await self._session.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.document_id == document_id,
                DocumentEmbedding.is_current.is_(True),
            ),
        )
        return list(result.scalars())

    async def _get_current_ai_metadata(self, document_id: UUID) -> list[DocumentMetadataRecord]:
        result = await self._session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document_id,
                DocumentMetadataRecord.source == MetadataSource.AI.value,
                DocumentMetadataRecord.is_current.is_(True),
            ),
        )
        return list(result.scalars())
