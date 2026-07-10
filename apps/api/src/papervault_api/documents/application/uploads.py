import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.domain.document_types import get_document_type
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.domain.models import DocumentRecord
from papervault_api.documents.infrastructure.models import Document, DocumentVersion
from papervault_api.documents.infrastructure.repositories import document_record_from_model
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent

CHUNK_SIZE_BYTES = 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    owner_id: UUID
    actor_id: UUID
    filename: str
    content_type: str
    title: str | None = None
    document_type: str = "generic_pdf"


@dataclass(frozen=True, slots=True)
class UploadedDocument:
    document: DocumentRecord
    processing_task_id: str | None


class UnsupportedUploadTypeError(ValueError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"Unsupported upload content type: {content_type}")
        self.content_type = content_type


class UploadTooLargeError(ValueError):
    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(f"Upload exceeds maximum size of {max_size_bytes} bytes")
        self.max_size_bytes = max_size_bytes


class EmptyUploadError(ValueError):
    def __init__(self) -> None:
        super().__init__("Upload is empty")


class DocumentUploadService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        storage: ObjectStorage,
        processing_queue: DocumentProcessingQueue,
        bucket_name: str,
        max_upload_size_bytes: int,
    ) -> None:
        self._session = session
        self._storage = storage
        self._processing_queue = processing_queue
        self._bucket_name = bucket_name
        self._max_upload_size_bytes = max_upload_size_bytes

    async def upload_document(
        self,
        command: UploadDocumentCommand,
        stream: AsyncReadable,
    ) -> UploadedDocument:
        self._validate_content_type(command.content_type)
        get_document_type(command.document_type)

        staged_file = await self._stage_upload(stream)
        object_key = self._build_storage_key(
            owner_id=command.owner_id,
            filename=command.filename,
        )

        try:
            stored_object = await self._storage.put_file(
                source_path=staged_file.path,
                bucket=self._bucket_name,
                key=object_key,
                content_type=command.content_type,
                metadata={
                    "sha256": staged_file.sha256_hash,
                    "original-filename": command.filename,
                },
            )
            document = Document(
                owner_id=command.owner_id,
                title=command.title or title_from_filename(command.filename),
                original_filename=command.filename,
                content_type=command.content_type,
                file_size_bytes=staged_file.file_size_bytes,
                sha256_hash=staged_file.sha256_hash,
                storage_bucket=stored_object.bucket,
                storage_key=stored_object.key,
                storage_version_id=stored_object.version_id,
                status=DocumentStatus.UPLOADED.value,
                document_type=command.document_type,
            )
            self._session.add(document)
            await self._session.flush()
            self._session.add(
                DocumentVersion(
                    document_id=document.id,
                    version_number=1,
                    storage_bucket=stored_object.bucket,
                    storage_key=stored_object.key,
                    storage_version_id=stored_object.version_id,
                    sha256_hash=staged_file.sha256_hash,
                    file_size_bytes=staged_file.file_size_bytes,
                    created_by_id=command.actor_id,
                    change_reason="initial_upload",
                ),
            )
            self._session.add(
                TimelineEvent(
                    owner_id=command.owner_id,
                    actor_id=command.actor_id,
                    document_id=document.id,
                    event_type=TimelineEventType.DOCUMENT_UPLOADED.value,
                    payload={
                        "filename": command.filename,
                        "content_type": command.content_type,
                        "file_size_bytes": staged_file.file_size_bytes,
                    },
                ),
            )
            await self._session.flush()
            await self._session.refresh(document)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            await self._storage.delete_file(bucket=self._bucket_name, key=object_key)
            raise
        finally:
            staged_file.cleanup()

        processing_task_id = await self._enqueue_processing(document)
        return UploadedDocument(
            document=document_record_from_model(document),
            processing_task_id=processing_task_id,
        )

    async def _enqueue_processing(self, document: Document) -> str | None:
        try:
            task_id = self._processing_queue.enqueue_document_processing(document.id)
        except Exception:
            document.status = DocumentStatus.FAILED.value
            document.processing_error = (
                "Document processing could not be queued. Check the worker and retry."
            )
            await self._session.commit()
            await self._session.refresh(document)
            return None
        document.status = DocumentStatus.PENDING_PROCESSING.value
        await self._session.commit()
        await self._session.refresh(document)
        return task_id

    async def _stage_upload(self, stream: AsyncReadable) -> "StagedUpload":
        digest = hashlib.sha256()
        file_size_bytes = 0
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(prefix="papervault-upload-", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                while chunk := await stream.read(CHUNK_SIZE_BYTES):
                    file_size_bytes += len(chunk)
                    if file_size_bytes > self._max_upload_size_bytes:
                        raise UploadTooLargeError(self._max_upload_size_bytes)
                    digest.update(chunk)
                    temp_file.write(chunk)
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

        assert temp_path is not None
        if file_size_bytes == 0:
            temp_path.unlink(missing_ok=True)
            raise EmptyUploadError()

        return StagedUpload(
            path=temp_path,
            sha256_hash=digest.hexdigest(),
            file_size_bytes=file_size_bytes,
        )

    def _validate_content_type(self, content_type: str) -> None:
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise UnsupportedUploadTypeError(content_type)

    def _build_storage_key(self, *, owner_id: UUID, filename: str) -> str:
        object_id = uuid4()
        safe_filename = sanitize_filename(filename)
        return f"{owner_id}/originals/{object_id}/{safe_filename}"


@dataclass(frozen=True, slots=True)
class StagedUpload:
    path: Path
    sha256_hash: str
    file_size_bytes: int

    def cleanup(self) -> None:
        self.path.unlink(missing_ok=True)


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "document"
    sanitized = SAFE_FILENAME_PATTERN.sub("_", name)
    return sanitized[:180] or "document"


def title_from_filename(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Untitled document"
