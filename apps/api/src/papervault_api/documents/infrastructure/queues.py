from uuid import UUID

from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.worker.celery_app import celery_app


class CeleryDocumentProcessingQueue(DocumentProcessingQueue):
    def enqueue_document_processing(self, document_id: UUID) -> str:
        result = celery_app.send_task(
            "papervault.documents.process_document",
            args=[str(document_id)],
        )
        return str(result.id)
