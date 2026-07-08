from typing import Protocol
from uuid import UUID


class DocumentProcessingQueue(Protocol):
    def enqueue_document_processing(self, document_id: UUID) -> str:
        raise NotImplementedError
