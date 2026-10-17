import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from papervault_api.core.config import Settings
from papervault_api.documents.application.ai import DocumentAIAnalysisResult
from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.application.uploads import (
    DocumentUploadService,
    UploadDocumentCommand,
)
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.identity.infrastructure.models import User
from papervault_api.search.application.indexing import SearchIndexDocument
from papervault_api.search.application.service import DocumentSearchService, SearchRequest
from papervault_api.search.domain.enums import SearchMode
from papervault_api.worker.tasks import documents as worker


class UnavailableAnalysis:
    def analyze(self, text: str, current_document_type: str) -> DocumentAIAnalysisResult:
        raise ConnectionError("Analysis service unavailable")


class RecordingIndex:
    def __init__(self) -> None:
        self.documents: list[SearchIndexDocument] = []

    def ensure_index(self) -> None:
        pass

    def index_document(self, document: SearchIndexDocument) -> None:
        self.documents.append(document)

    def delete_document(self, document_id: object) -> None:
        raise AssertionError("The extracted document must remain indexed")


def text_pdf() -> bytes:
    from pypdf.generic import DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Service reference ZXQ918273) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class PdfStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    async def put_file(
        self,
        *,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        self.objects[(bucket, key)] = source_path.read_bytes()
        return StoredObject(bucket=bucket, key=key, version_id="original")

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        destination.write_bytes(self.objects[(bucket, key)])

    async def delete_file(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


class PdfUpload:
    def __init__(self, content: bytes) -> None:
        self.stream = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class TestQueue:
    __test__ = False

    def enqueue_document_processing(self, document_id: object) -> str:
        return f"process-{document_id}"


@pytest.mark.parametrize("lost_acknowledgement", [False, True])
async def test_fast_worker_completion_is_not_overwritten_by_upload_response(
    session: AsyncSession, lost_acknowledgement: bool
) -> None:
    user = User(email="fast-worker@example.com")
    session.add(user)
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)

    async def complete_in_worker(document_id: UUID) -> None:
        async with factory() as db:
            document = await db.get(Document, document_id)
            assert document is not None
            assert document.status == "pending_processing"
            document.status = "ready"
            await db.commit()

    class FastQueue:
        def enqueue_document_processing(self, document_id: UUID) -> str:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: asyncio.run(complete_in_worker(document_id))).result(timeout=5)
            if lost_acknowledgement:
                raise ConnectionError("Queue acknowledgement lost after delivery")
            return "completed-task"

    uploaded = await DocumentUploadService(
        session=session,
        storage=PdfStorage(),
        processing_queue=FastQueue(),
        bucket_name="documents",
        max_upload_size_bytes=1024 * 1024,
    ).upload_document(
        UploadDocumentCommand(
            owner_id=user.id,
            actor_id=user.id,
            filename="fast.pdf",
            content_type="application/pdf",
        ),
        PdfUpload(text_pdf()),
    )
    assert uploaded.document.status == "ready"


@pytest.mark.parametrize("delivery", ["inline", "queued", "publication_failed"])
async def test_real_pdf_text_is_searchable_and_indexed_even_when_analysis_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, delivery: str
) -> None:
    user = User(email="ingestion-check@example.com")
    session.add(user)
    await session.flush()
    await session.commit()
    owner_id = user.id
    storage = PdfStorage()
    source = text_pdf()
    uploaded = await DocumentUploadService(
        session=session,
        storage=storage,
        processing_queue=TestQueue(),
        bucket_name="documents",
        max_upload_size_bytes=1024 * 1024,
    ).upload_document(
        UploadDocumentCommand(
            owner_id=owner_id,
            actor_id=owner_id,
            filename="service.pdf",
            content_type="application/pdf",
        ),
        PdfUpload(source),
    )
    document_id = uploaded.document.id
    document = await session.get(Document, document_id)
    assert document is not None
    assert uploaded.processing_task_id == f"process-{document_id}"
    assert list(storage.objects.values()) == [source]
    index = RecordingIndex()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)

    @asynccontextmanager
    async def worker_session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            yield db

    monkeypatch.setattr(worker, "AsyncSessionFactory", worker_session)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: Settings(ai_enabled=True, enrichment_queue_enabled=delivery != "inline"),
    )
    monkeypatch.setattr(worker, "S3ObjectStorage", lambda **kwargs: storage)
    monkeypatch.setattr(worker, "build_document_ai_provider", lambda *args: UnavailableAnalysis())
    monkeypatch.setattr(worker, "build_search_document_index", lambda settings: index)
    published: list[tuple[str, list[str], str]] = []

    def publish(name: str, *, args: list[str], queue: str) -> None:
        if delivery == "publication_failed":
            raise ConnectionError("Broker unavailable")
        published.append((name, args, queue))

    monkeypatch.setattr(worker.celery_app, "send_task", publish)

    await worker._process_document(document_id)
    await session.refresh(document)
    extraction = await session.scalar(
        select(DocumentTextExtraction).where(
            DocumentTextExtraction.document_id == document_id,
            DocumentTextExtraction.is_current.is_(True),
        )
    )
    assert document.status == "ready"
    assert document.processing_error is None
    assert document.review_status == "pending"
    assert document.review_reasons == [
        "analysis_pending:metadata" if delivery == "queued" else "analysis_failed:metadata"
    ]
    assert extraction is not None and "ZXQ918273" in (extraction.content_text or "")
    assert index.documents
    assert index.documents[0].status == "ready"
    assert "ZXQ918273" in (index.documents[0].text or "")
    results = await DocumentSearchService(
        session=session, embedding_provider_name="local", embedding_dimensions=64
    ).search(SearchRequest(owner_id=owner_id, query="ZXQ918273", mode=SearchMode.KEYWORD))
    assert [result.document_id for result in results] == [document_id]
    if delivery == "queued":
        assert published == [
            (
                "papervault.documents.enrich_document",
                [str(document_id), str(extraction.id)],
                "papervault-enrichment",
            )
        ]
        await worker._mark_enrichment_failed(document_id, uuid4())
        await session.refresh(document)
        assert document.review_reasons == ["analysis_pending:metadata"]
        # The searchable text above is available before the model has run.
        await worker._enrich_document(document_id, extraction.id)
        await session.refresh(document)
        assert document.status == "ready"
        assert document.review_reasons == ["analysis_failed:metadata"]
    else:
        assert not published
