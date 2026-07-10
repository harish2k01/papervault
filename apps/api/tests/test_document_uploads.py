import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.base import Base
from papervault_api.db.session import get_session
from papervault_api.documents.api.dependencies import (
    get_document_processing_queue,
    get_object_storage,
)
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.main import create_app


class FakeObjectStorage:
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
        return StoredObject(bucket=bucket, key=key, version_id="fake-version")

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        destination.write_bytes(self.objects[(bucket, key)])

    async def delete_file(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


class FakeDocumentProcessingQueue(DocumentProcessingQueue):
    def enqueue_document_processing(self, document_id: UUID) -> str:
        return f"task-{document_id}"


def build_upload_test_app() -> tuple[FastAPI, FakeObjectStorage, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = FakeObjectStorage()

    async def override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_document_processing_queue] = lambda: FakeDocumentProcessingQueue()

    return app, storage, engine


def test_upload_document_persists_file_and_returns_document_response() -> None:
    app, storage, engine = build_upload_test_app()

    user_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            "/documents/uploads",
            headers={
                "X-PaperVault-User-Id": str(user_id),
                "X-PaperVault-User-Email": "person@example.com",
            },
            data={"document_type": "generic_pdf"},
            files={"file": ("statement.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["owner_id"] == str(user_id)
    assert body["document"]["original_filename"] == "statement.pdf"
    assert body["document"]["status"] == "pending_processing"
    assert body["processing_task_id"].startswith("task-")
    assert len(storage.objects) == 1
    asyncio.run(engine.dispose())


def test_upload_rejects_unsupported_content_type() -> None:
    app, _storage, engine = build_upload_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/documents/uploads",
            headers={"X-PaperVault-User-Id": str(uuid4())},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )

    assert response.status_code == 415
    asyncio.run(engine.dispose())


def test_only_stale_pending_document_can_be_requeued() -> None:
    app, _storage, engine = build_upload_test_app()
    user_id = uuid4()
    headers = {
        "X-PaperVault-User-Id": str(user_id),
        "X-PaperVault-User-Email": "person@example.com",
    }

    with TestClient(app) as client:
        upload_response = client.post(
            "/documents/uploads",
            headers=headers,
            files={"file": ("statement.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]

        queued_response = client.post(f"/documents/{document_id}/reprocess", headers=headers)

    assert queued_response.status_code == 409

    async def make_document_stale() -> None:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            document = await session.get(Document, UUID(document_id))
            assert document is not None
            document.updated_at = datetime.now(UTC) - timedelta(minutes=3)
            await session.commit()

    asyncio.run(make_document_stale())

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/reprocess", headers=headers)

    assert response.status_code == 200
    assert response.json()["document"]["status"] == "pending_processing"
    assert response.json()["processing_task_id"] == f"task-{document_id}"
    asyncio.run(engine.dispose())


def test_document_lifecycle_routes_update_metadata_and_archive() -> None:
    app, _storage, engine = build_upload_test_app()
    app.dependency_overrides[get_settings] = lambda: Settings(search_index_enabled=False)

    user_id = uuid4()
    headers = {
        "X-PaperVault-User-Id": str(user_id),
        "X-PaperVault-User-Email": "person@example.com",
    }
    with TestClient(app) as client:
        upload_response = client.post(
            "/documents/uploads",
            headers=headers,
            data={"document_type": "invoice"},
            files={"file": ("invoice.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
        assert upload_response.status_code == 201
        document_id = upload_response.json()["document"]["id"]

        update_response = client.patch(
            f"/documents/{document_id}",
            headers=headers,
            json={"title": "iPad Invoice", "issuer": "Apple Store"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "iPad Invoice"

        metadata_response = client.put(
            f"/documents/{document_id}/metadata",
            headers=headers,
            json={
                "schema_name": "invoice",
                "data": {
                    "vendor": "Apple Store",
                    "purchase_date": "2026-07-01",
                    "total_amount": 999,
                },
            },
        )
        assert metadata_response.status_code == 200
        assert metadata_response.json()["data"]["vendor"] == "Apple Store"

        detail_response = client.get(f"/documents/{document_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["document"]["issuer"] == "Apple Store"
        assert detail["document"]["document_date"] == "2026-07-01"
        assert detail["versions"][0]["version_number"] == 1

        archive_response = client.post(f"/documents/{document_id}/archive", headers=headers)
        assert archive_response.status_code == 200
        assert archive_response.json()["status"] == "archived"

        list_response = client.get("/documents", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json() == []

    asyncio.run(engine.dispose())


def test_document_text_search_returns_page_aware_matches() -> None:
    app, _storage, engine = build_upload_test_app()
    user_id = uuid4()
    headers = {
        "X-PaperVault-User-Id": str(user_id),
        "X-PaperVault-User-Email": "reader@example.com",
    }

    with TestClient(app) as client:
        upload_response = client.post(
            "/documents/uploads",
            headers=headers,
            files={"file": ("salary.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
        document_id = UUID(upload_response.json()["document"]["id"])
        asyncio.run(seed_text_pages(engine, document_id))

        response = client.get(
            f"/documents/{document_id}/text-search",
            headers=headers,
            params={"query": "salary"},
        )
        invalid_response = client.get(
            f"/documents/{document_id}/text-search",
            headers=headers,
            params={"query": "  "},
        )

    assert response.status_code == 200
    assert invalid_response.status_code == 422
    assert response.json() == {
        "query": "salary",
        "total_matches": 2,
        "page_mapping_available": True,
        "matches": [
            {
                "page_number": 1,
                "before": "January",
                "match": "salary",
                "after": "was 1000",
            },
            {
                "page_number": 2,
                "before": "February",
                "match": "salary",
                "after": "was 1100",
            },
        ],
    }
    asyncio.run(engine.dispose())


async def seed_text_pages(engine: AsyncEngine, document_id: UUID) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        extraction = DocumentTextExtraction(
            document_id=document_id,
            source="embedded_text",
            status="succeeded",
            content_text="January salary was 1000\n\nFebruary salary was 1100",
            page_count=2,
            is_current=True,
        )
        session.add(extraction)
        await session.flush()
        session.add_all(
            (
                DocumentTextPage(
                    text_extraction_id=extraction.id,
                    page_number=1,
                    content_text="January salary was 1000",
                ),
                DocumentTextPage(
                    text_extraction_id=extraction.id,
                    page_number=2,
                    content_text="February salary was 1100",
                ),
            )
        )
        await session.commit()
