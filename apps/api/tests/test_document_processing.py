from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.extraction import (
    OcrTextBlock,
    TextExtractionResult,
    TextExtractor,
)
from papervault_api.documents.application.processing import DocumentProcessingService
from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextBlock,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.identity.infrastructure.models import User


class FakeObjectStorage:
    async def put_file(
        self,
        *,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        raise NotImplementedError

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        destination.write_bytes(b"document")

    async def delete_file(self, *, bucket: str, key: str) -> None:
        raise NotImplementedError


class StaticTextExtractor(TextExtractor):
    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        return TextExtractionResult(
            source=TextExtractionSource.EMBEDDED_TEXT,
            status=TextExtractionStatus.SUCCEEDED,
            content_text="Hello from a PDF",
            page_texts=("Hello from a PDF",),
            page_blocks=(
                (
                    OcrTextBlock(
                        text="Hello",
                        left_ratio=0.1,
                        top_ratio=0.2,
                        width_ratio=0.3,
                        height_ratio=0.05,
                        confidence_score=0.94,
                    ),
                ),
            ),
            page_count=1,
            extractor="static",
        )


async def test_processing_service_records_current_text_extraction(session: AsyncSession) -> None:
    user = User(email="reader@example.com")
    session.add(user)
    await session.flush()

    document = Document(
        owner_id=user.id,
        title="Document",
        original_filename="document.pdf",
        content_type="application/pdf",
        file_size_bytes=8,
        sha256_hash="b" * 64,
        storage_bucket="documents",
        storage_key=f"{uuid4()}/document.pdf",
        document_type="generic_pdf",
    )
    session.add(document)
    await session.commit()

    service = DocumentProcessingService(
        session=session,
        storage=FakeObjectStorage(),
        text_extractor=StaticTextExtractor(),
    )

    await service.process_document(document.id)

    refreshed_document = await session.get(Document, document.id)
    result = await session.execute(
        select(DocumentTextExtraction).where(DocumentTextExtraction.document_id == document.id),
    )
    extraction = result.scalar_one()
    page = (
        await session.execute(
            select(DocumentTextPage).where(DocumentTextPage.text_extraction_id == extraction.id)
        )
    ).scalar_one()
    block = (
        await session.execute(
            select(DocumentTextBlock).where(DocumentTextBlock.text_extraction_id == extraction.id)
        )
    ).scalar_one()

    assert refreshed_document is not None
    assert refreshed_document.status == DocumentStatus.READY.value
    assert refreshed_document.processing_started_at is not None
    assert refreshed_document.processing_completed_at is not None
    assert refreshed_document.processing_error is None
    assert extraction.status == TextExtractionStatus.SUCCEEDED.value
    assert extraction.content_text == "Hello from a PDF"
    assert extraction.is_current is True
    assert page.page_number == 1
    assert page.content_text == "Hello from a PDF"
    assert block.page_number == 1
    assert block.text == "Hello"
    assert float(block.left_ratio) == 0.1
    assert float(block.confidence_score or 0) == 0.94


async def test_processing_service_does_not_resurrect_archived_document(
    session: AsyncSession,
) -> None:
    user = User(email="archived-reader@example.com")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Archived duplicate",
        original_filename="duplicate.pdf",
        content_type="application/pdf",
        file_size_bytes=8,
        sha256_hash="c" * 64,
        storage_bucket="documents",
        storage_key=f"{uuid4()}/duplicate.pdf",
        document_type="generic_pdf",
        status=DocumentStatus.ARCHIVED.value,
        archived_at=datetime.now(UTC),
    )
    session.add(document)
    await session.commit()

    service = DocumentProcessingService(
        session=session,
        storage=FakeObjectStorage(),
        text_extractor=StaticTextExtractor(),
    )
    await service.process_document(document.id)

    refreshed_document = await session.get(Document, document.id)
    extractions = (
        await session.execute(
            select(DocumentTextExtraction).where(DocumentTextExtraction.document_id == document.id)
        )
    ).scalars()

    assert refreshed_document is not None
    assert refreshed_document.status == DocumentStatus.ARCHIVED.value
    assert tuple(extractions) == ()
