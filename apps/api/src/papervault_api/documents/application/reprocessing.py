from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.processing import mark_document_processing_failed
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.infrastructure.models import Document
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent


class InvalidReprocessingRequestError(ValueError):
    pass


class ReprocessingQueueError(RuntimeError):
    pass


PENDING_REPROCESS_AFTER = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class ReprocessingCommand:
    owner_id: UUID
    actor_id: UUID
    document_id: UUID


@dataclass(frozen=True, slots=True)
class ReprocessingResult:
    document: Document
    processing_task_id: str


class DocumentReprocessingService:
    def __init__(
        self,
        session: AsyncSession,
        processing_queue: DocumentProcessingQueue,
    ) -> None:
        self._session = session
        self._processing_queue = processing_queue

    async def request(self, command: ReprocessingCommand) -> ReprocessingResult | None:
        document = await self._session.get(Document, command.document_id)
        if document is None or document.owner_id != command.owner_id:
            return None
        if document.status == DocumentStatus.ARCHIVED.value or document.archived_at is not None:
            raise InvalidReprocessingRequestError("Archived documents cannot be reprocessed")
        if document.status == DocumentStatus.PROCESSING.value:
            raise InvalidReprocessingRequestError("Document processing is already running")
        if document.status == DocumentStatus.PENDING_PROCESSING.value:
            updated_at = document.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            if datetime.now(UTC) - updated_at < PENDING_REPROCESS_AFTER:
                raise InvalidReprocessingRequestError("Document processing is still queued")

        document.status = DocumentStatus.PENDING_PROCESSING.value
        document.processing_error = None
        document.processing_started_at = None
        document.processing_completed_at = None
        self._session.add(
            TimelineEvent(
                owner_id=command.owner_id,
                actor_id=command.actor_id,
                document_id=document.id,
                event_type=TimelineEventType.METADATA_EDITED.value,
                payload={"action": "reprocessing_requested"},
            )
        )
        await self._session.commit()

        try:
            task_id = self._processing_queue.enqueue_document_processing(document.id)
        except Exception as exc:
            await mark_document_processing_failed(
                self._session,
                document.id,
                message="Document processing could not be queued. Check the worker and retry.",
            )
            raise ReprocessingQueueError("Document processing could not be queued") from exc

        await self._session.refresh(document)
        return ReprocessingResult(document=document, processing_task_id=task_id)
