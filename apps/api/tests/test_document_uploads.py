import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from papervault_api.db.base import Base
from papervault_api.db.session import get_session
from papervault_api.documents.api.dependencies import (
    get_document_processing_queue,
    get_object_storage,
)
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.storage import StoredObject
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
