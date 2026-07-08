from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.extraction import TextExtractionResult, TextExtractor
from papervault_api.documents.application.processing import DocumentProcessingService
from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
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

    assert refreshed_document is not None
    assert refreshed_document.status == DocumentStatus.READY.value
    assert extraction.status == TextExtractionStatus.SUCCEEDED.value
    assert extraction.content_text == "Hello from a PDF"
    assert extraction.is_current is True
