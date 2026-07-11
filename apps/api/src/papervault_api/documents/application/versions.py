import difflib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.processing import mark_document_processing_failed
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.application.uploads import (
    AsyncReadable,
    build_storage_key,
    stage_upload,
    validate_content_type,
)
from papervault_api.documents.domain.enums import DocumentReviewStatus, DocumentStatus
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextExtraction,
    DocumentVersion,
)
from papervault_api.notifications.infrastructure.models import Notification
from papervault_api.tags.infrastructure.models import DocumentTag
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent


class InvalidVersionChangeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VersionChangeResult:
    document: Document
    version: DocumentVersion
    processing_task_id: str | None


@dataclass(frozen=True, slots=True)
class VersionComparison:
    from_version: DocumentVersion
    to_version: DocumentVersion
    source_changed: bool
    text_available: bool
    added_lines: int
    removed_lines: int
    diff_lines: tuple[str, ...]


class DocumentVersionService:
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

    async def replace_source(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        filename: str,
        content_type: str,
        stream: AsyncReadable,
        change_reason: str | None,
    ) -> VersionChangeResult | None:
        validate_content_type(content_type)
        document = await self._get_locked_document(document_id, owner_id)
        if document is None:
            return None
        self._validate_change(document)

        staged = await stage_upload(stream, self._max_upload_size_bytes)
        object_key = build_storage_key(owner_id=owner_id, filename=filename)
        try:
            stored = await self._storage.put_file(
                source_path=staged.path,
                bucket=self._bucket_name,
                key=object_key,
                content_type=content_type,
                metadata={
                    "sha256": staged.sha256_hash,
                    "original-filename": filename,
                },
            )
            version = await self._activate_version(
                document=document,
                actor_id=actor_id,
                original_filename=filename,
                content_type=content_type,
                storage_bucket=stored.bucket,
                storage_key=stored.key,
                storage_version_id=stored.version_id,
                sha256_hash=staged.sha256_hash,
                file_size_bytes=staged.file_size_bytes,
                change_reason=(change_reason or "source_replaced")[:255],
                action="source_replaced",
            )
            await self._session.commit()
            await self._session.refresh(version)
            await self._session.refresh(document)
        except Exception:
            await self._session.rollback()
            await self._storage.delete_file(bucket=self._bucket_name, key=object_key)
            raise
        finally:
            staged.cleanup()
        return await self._enqueue(document, version)

    async def restore_version(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> VersionChangeResult | None:
        document = await self._get_locked_document(document_id, owner_id)
        if document is None:
            return None
        self._validate_change(document)
        target = await self._session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        if target is None:
            raise InvalidVersionChangeError("Version not found")
        if target.is_current:
            raise InvalidVersionChangeError("The selected version is already current")

        version = await self._activate_version(
            document=document,
            actor_id=actor_id,
            original_filename=target.original_filename,
            content_type=target.content_type,
            storage_bucket=target.storage_bucket,
            storage_key=target.storage_key,
            storage_version_id=target.storage_version_id,
            sha256_hash=target.sha256_hash,
            file_size_bytes=target.file_size_bytes,
            change_reason=f"restored_version_{target.version_number}",
            action="version_restored",
            restored_from=target.version_number,
        )
        await self._session.commit()
        await self._session.refresh(version)
        await self._session.refresh(document)
        return await self._enqueue(document, version)

    async def compare_versions(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        from_version_id: UUID,
        to_version_id: UUID,
    ) -> VersionComparison | None:
        document = await self._session.scalar(
            select(Document.id).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            )
        )
        if document is None:
            return None
        versions = list(
            (
                await self._session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.id.in_((from_version_id, to_version_id)),
                    )
                )
            ).scalars()
        )
        by_id = {version.id: version for version in versions}
        if from_version_id not in by_id or to_version_id not in by_id:
            raise InvalidVersionChangeError("Version not found")

        from_text = await self._version_text(from_version_id)
        to_text = await self._version_text(to_version_id)
        diff = tuple(
            difflib.unified_diff(
                (from_text or "").splitlines(),
                (to_text or "").splitlines(),
                fromfile=f"version-{by_id[from_version_id].version_number}",
                tofile=f"version-{by_id[to_version_id].version_number}",
                lineterm="",
            )
        )[:500]
        return VersionComparison(
            from_version=by_id[from_version_id],
            to_version=by_id[to_version_id],
            source_changed=(by_id[from_version_id].sha256_hash != by_id[to_version_id].sha256_hash),
            text_available=from_text is not None and to_text is not None,
            added_lines=sum(
                1 for line in diff if line.startswith("+") and not line.startswith("+++")
            ),
            removed_lines=sum(
                1 for line in diff if line.startswith("-") and not line.startswith("---")
            ),
            diff_lines=diff,
        )

    async def get_version(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        result = await self._session.execute(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.owner_id == owner_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.id == version_id,
            )
        )
        return result.scalar_one_or_none()

    async def _activate_version(
        self,
        *,
        document: Document,
        actor_id: UUID,
        original_filename: str,
        content_type: str,
        storage_bucket: str,
        storage_key: str,
        storage_version_id: str | None,
        sha256_hash: str,
        file_size_bytes: int,
        change_reason: str,
        action: str,
        restored_from: int | None = None,
    ) -> DocumentVersion:
        next_number = (
            await self._session.scalar(
                select(func.max(DocumentVersion.version_number)).where(
                    DocumentVersion.document_id == document.id
                )
            )
            or 0
        ) + 1
        await self._session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .values(is_current=False)
        )
        version = DocumentVersion(
            document_id=document.id,
            version_number=next_number,
            original_filename=original_filename,
            content_type=content_type,
            storage_bucket=storage_bucket,
            storage_key=storage_key,
            storage_version_id=storage_version_id,
            sha256_hash=sha256_hash,
            file_size_bytes=file_size_bytes,
            created_by_id=actor_id,
            change_reason=change_reason,
            is_current=True,
        )
        self._session.add(version)
        document.original_filename = original_filename
        document.content_type = content_type
        document.storage_bucket = storage_bucket
        document.storage_key = storage_key
        document.storage_version_id = storage_version_id
        document.sha256_hash = sha256_hash
        document.file_size_bytes = file_size_bytes
        document.status = DocumentStatus.PENDING_PROCESSING.value
        document.page_count = None
        document.summary = None
        document.processing_error = None
        document.processing_started_at = None
        document.processing_completed_at = None
        document.review_status = DocumentReviewStatus.PENDING.value
        document.review_reasons = ["analysis_pending:replacement"]
        document.reviewed_at = None
        document.reviewed_by_id = None
        document.review_note = None

        await self._session.execute(
            update(DocumentTextExtraction)
            .where(DocumentTextExtraction.document_id == document.id)
            .values(is_current=False)
        )
        await self._session.execute(
            update(DocumentMetadataRecord)
            .where(DocumentMetadataRecord.document_id == document.id)
            .values(is_current=False)
        )
        await self._session.execute(
            update(DocumentAIAnalysis)
            .where(DocumentAIAnalysis.document_id == document.id)
            .values(is_current=False)
        )
        await self._session.execute(
            update(DocumentEmbedding)
            .where(DocumentEmbedding.document_id == document.id)
            .values(is_current=False)
        )
        await self._session.execute(
            delete(DocumentTag).where(
                DocumentTag.document_id == document.id,
                DocumentTag.source == "ai",
            )
        )
        await self._session.execute(
            delete(Notification).where(Notification.document_id == document.id)
        )
        payload: dict[str, object] = {
            "action": action,
            "version_number": next_number,
            "filename": original_filename,
        }
        if restored_from is not None:
            payload["restored_from_version"] = restored_from
        self._session.add(
            TimelineEvent(
                owner_id=document.owner_id,
                actor_id=actor_id,
                document_id=document.id,
                event_type=TimelineEventType.VERSION_CREATED.value,
                payload=payload,
            )
        )
        await self._session.flush()
        return version

    async def _enqueue(
        self,
        document: Document,
        version: DocumentVersion,
    ) -> VersionChangeResult:
        try:
            task_id = self._processing_queue.enqueue_document_processing(document.id)
        except Exception:
            await mark_document_processing_failed(
                self._session,
                document.id,
                message=(
                    "The new version was saved but processing could not be queued. "
                    "Retry processing."
                ),
            )
            task_id = None
        await self._session.refresh(document)
        return VersionChangeResult(document=document, version=version, processing_task_id=task_id)

    async def _get_locked_document(self, document_id: UUID, owner_id: UUID) -> Document | None:
        result = await self._session.execute(
            select(Document)
            .where(Document.id == document_id, Document.owner_id == owner_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_change(document: Document) -> None:
        if document.status == DocumentStatus.ARCHIVED.value or document.archived_at is not None:
            raise InvalidVersionChangeError("Archived documents cannot change source versions")
        if document.status in {
            DocumentStatus.PROCESSING.value,
            DocumentStatus.PENDING_PROCESSING.value,
        }:
            raise InvalidVersionChangeError("Wait for current document processing to finish")

    async def _version_text(self, version_id: UUID) -> str | None:
        return await self._session.scalar(
            select(DocumentTextExtraction.content_text)
            .where(
                DocumentTextExtraction.document_version_id == version_id,
                DocumentTextExtraction.status == "succeeded",
            )
            .order_by(DocumentTextExtraction.created_at.desc())
            .limit(1)
        )
