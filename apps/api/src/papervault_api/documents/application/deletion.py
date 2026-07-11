from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.infrastructure.models import Document, DocumentVersion


@dataclass(frozen=True, slots=True)
class StoredDocumentObject:
    bucket: str
    key: str


class DocumentDeletionService:
    def __init__(self, *, session: AsyncSession, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage

    async def delete_document(self, *, owner_id: UUID, document_id: UUID) -> bool:
        document = await self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            ),
        )
        if document is None:
            return False

        version_objects = await self._session.execute(
            select(DocumentVersion.storage_bucket, DocumentVersion.storage_key).where(
                DocumentVersion.document_id == document_id,
            ),
        )
        objects = {
            StoredDocumentObject(document.storage_bucket, document.storage_key),
            *(StoredDocumentObject(bucket, key) for bucket, key in version_objects),
        }

        await self._session.delete(document)
        await self._session.flush()
        try:
            for stored_object in objects:
                await self._storage.delete_file(
                    bucket=stored_object.bucket,
                    key=stored_object.key,
                )
        except Exception:
            await self._session.rollback()
            raise

        await self._session.commit()
        return True
