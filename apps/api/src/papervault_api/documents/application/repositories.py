from typing import Protocol
from uuid import UUID

from papervault_api.documents.domain.models import DocumentRecord, NewDocumentRecord


class DocumentRepository(Protocol):
    async def add(self, document: NewDocumentRecord) -> DocumentRecord:
        raise NotImplementedError

    async def get_for_owner(self, document_id: UUID, owner_id: UUID) -> DocumentRecord | None:
        raise NotImplementedError
