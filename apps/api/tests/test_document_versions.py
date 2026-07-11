from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.application.versions import DocumentVersionService
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentVersion,
)
from papervault_api.identity.infrastructure.models import User


class MemoryStream:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._read = False

    async def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content


class MemoryStorage:
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
        return StoredObject(bucket=bucket, key=key)

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        destination.write_bytes(self.objects[(bucket, key)])

    async def delete_file(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


class RecordingQueue:
    def __init__(self) -> None:
        self.document_ids: list[UUID] = []

    def enqueue_document_processing(self, document_id: UUID) -> str:
        self.document_ids.append(document_id)
        return f"task-{document_id}"


async def test_source_replacement_restore_and_comparison_preserve_history(
    session: AsyncSession,
) -> None:
    user = User(email="versions@example.com")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Policy",
        original_filename="policy-v1.pdf",
        content_type="application/pdf",
        file_size_bytes=10,
        sha256_hash="1" * 64,
        storage_bucket="documents",
        storage_key="versions/v1.pdf",
        status=DocumentStatus.READY.value,
        document_type="insurance_policy",
    )
    session.add(document)
    await session.flush()
    first_version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        original_filename="policy-v1.pdf",
        content_type="application/pdf",
        storage_bucket="documents",
        storage_key="versions/v1.pdf",
        sha256_hash="1" * 64,
        file_size_bytes=10,
        created_by_id=user.id,
        change_reason="initial_upload",
        is_current=True,
    )
    session.add(first_version)
    await session.flush()
    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            document_version_id=first_version.id,
            source=TextExtractionSource.EMBEDDED_TEXT.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text="Policy coverage INR 100000",
            page_count=1,
            is_current=True,
        )
    )
    await session.commit()

    storage = MemoryStorage()
    storage.objects[("documents", "versions/v1.pdf")] = b"version-one"
    queue = RecordingQueue()
    service = DocumentVersionService(
        session=session,
        storage=storage,
        processing_queue=queue,
        bucket_name="documents",
        max_upload_size_bytes=1024,
    )

    replacement = await service.replace_source(
        owner_id=user.id,
        actor_id=user.id,
        document_id=document.id,
        filename="policy-v2.pdf",
        content_type="application/pdf",
        stream=MemoryStream(b"Policy coverage INR 200000"),
        change_reason="renewed policy",
    )

    assert replacement is not None
    assert replacement.version.version_number == 2
    assert replacement.version.is_current is True
    assert replacement.document.status == DocumentStatus.PENDING_PROCESSING.value
    assert queue.document_ids == [document.id]
    await session.refresh(first_version)
    assert first_version.is_current is False

    replacement.document.status = DocumentStatus.READY.value
    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            document_version_id=replacement.version.id,
            source=TextExtractionSource.EMBEDDED_TEXT.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text="Policy coverage INR 200000",
            page_count=1,
            is_current=True,
        )
    )
    await session.commit()

    comparison = await service.compare_versions(
        owner_id=user.id,
        document_id=document.id,
        from_version_id=first_version.id,
        to_version_id=replacement.version.id,
    )
    assert comparison is not None
    assert comparison.source_changed is True
    assert comparison.text_available is True
    assert comparison.added_lines == 1
    assert comparison.removed_lines == 1

    restored = await service.restore_version(
        owner_id=user.id,
        actor_id=user.id,
        document_id=document.id,
        version_id=first_version.id,
    )
    assert restored is not None
    assert restored.version.version_number == 3
    assert restored.version.sha256_hash == first_version.sha256_hash
    assert restored.document.original_filename == "policy-v1.pdf"
    versions = (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number)
        )
    ).scalars()
    assert [version.is_current for version in versions] == [False, False, True]
