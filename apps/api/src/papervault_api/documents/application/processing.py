from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.extraction import (
    TextExtractor,
    sanitize_extracted_text,
)
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.domain.enums import (
    DocumentReviewStatus,
    DocumentStatus,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextBlock,
    DocumentTextExtraction,
    DocumentTextPage,
)


class DocumentProcessingService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        text_extractor: TextExtractor,
    ) -> None:
        self._session = session
        self._storage = storage
        self._text_extractor = text_extractor

    async def process_document(self, document_id: UUID) -> None:
        document = await self._session.get(Document, document_id)
        if document is None:
            return
        if document.status == DocumentStatus.ARCHIVED.value or document.archived_at is not None:
            return

        document.status = DocumentStatus.PROCESSING.value
        document.processing_error = None
        document.processing_started_at = datetime.now(UTC)
        document.processing_completed_at = None
        await self._session.commit()

        with TemporaryDirectory(prefix="papervault-process-") as temp_dir:
            file_path = Path(temp_dir) / "source"
            await self._storage.download_to_file(
                bucket=document.storage_bucket,
                key=document.storage_key,
                destination=file_path,
            )
            result = self._text_extractor.extract(file_path, document.content_type)

        content_text = (
            sanitize_extracted_text(result.content_text)
            if result.content_text is not None
            else None
        )
        page_texts = tuple(sanitize_extracted_text(text) for text in result.page_texts)

        await self._mark_existing_extractions_not_current(document.id)
        extraction = DocumentTextExtraction(
            document_id=document.id,
            source=result.source.value,
            status=result.status.value,
            content_text=content_text,
            page_count=result.page_count,
            language=result.language,
            confidence_score=result.confidence_score,
            extractor=result.extractor,
            error_message=result.error_message,
            is_current=True,
        )
        self._session.add(extraction)
        await self._session.flush()
        self._session.add_all(
            DocumentTextPage(
                text_extraction_id=extraction.id,
                page_number=page_number,
                content_text=content_text,
            )
            for page_number, content_text in enumerate(page_texts, start=1)
        )
        self._session.add_all(
            DocumentTextBlock(
                text_extraction_id=extraction.id,
                page_number=page_number,
                block_index=block_index,
                text=sanitize_extracted_text(block.text),
                left_ratio=Decimal(str(block.left_ratio)),
                top_ratio=Decimal(str(block.top_ratio)),
                width_ratio=Decimal(str(block.width_ratio)),
                height_ratio=Decimal(str(block.height_ratio)),
                confidence_score=(
                    Decimal(str(block.confidence_score))
                    if block.confidence_score is not None
                    else None
                ),
            )
            for page_number, blocks in enumerate(result.page_blocks, start=1)
            for block_index, block in enumerate(blocks)
        )
        await self._session.refresh(document, attribute_names=["status", "archived_at"])
        document.page_count = result.page_count or document.page_count
        if document.status != DocumentStatus.ARCHIVED.value and document.archived_at is None:
            document.status = (
                DocumentStatus.READY.value
                if result.status is TextExtractionStatus.SUCCEEDED
                else DocumentStatus.FAILED.value
            )
            document.processing_error = (
                result.error_message
                if result.status is not TextExtractionStatus.SUCCEEDED
                else None
            )
            document.processing_completed_at = datetime.now(UTC)
            if result.status is TextExtractionStatus.SUCCEEDED:
                document.review_status = DocumentReviewStatus.PENDING.value
                document.review_reasons = ["analysis_pending:metadata"]
        await self._session.commit()

    async def _mark_existing_extractions_not_current(self, document_id: UUID) -> None:
        for extraction in await self._load_current_extractions(document_id):
            extraction.is_current = False

    async def _load_current_extractions(self, document_id: UUID) -> list[DocumentTextExtraction]:
        await self._session.flush()
        result = await self._session.execute(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
            ),
        )
        return list(result.scalars())


async def mark_document_processing_failed(
    session: AsyncSession,
    document_id: UUID,
    *,
    message: str,
) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        return
    if document.status == DocumentStatus.ARCHIVED.value or document.archived_at is not None:
        return
    document.status = DocumentStatus.FAILED.value
    document.processing_error = message[:2000]
    document.processing_completed_at = datetime.now(UTC)
    await session.commit()
