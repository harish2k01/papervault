from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.domain.enums import DocumentSourceKind, DocumentStatus
from papervault_api.documents.domain.models import DocumentRecord, NewDocumentRecord
from papervault_api.documents.infrastructure.models import Document


class SqlAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: NewDocumentRecord) -> DocumentRecord:
        model = Document(
            owner_id=document.owner_id,
            title=document.title,
            original_filename=document.original_filename,
            content_type=document.content_type,
            file_size_bytes=document.file_size_bytes,
            sha256_hash=document.sha256_hash,
            storage_bucket=document.storage_bucket,
            storage_key=document.storage_key,
            storage_version_id=document.storage_version_id,
            source_kind=document.source_kind.value,
            status=DocumentStatus.UPLOADED.value,
            document_type=document.document_type,
            document_date=document.document_date,
            issuer=document.issuer,
            organization=document.organization,
            page_count=document.page_count,
            language=document.language,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return document_record_from_model(model)

    async def get_for_owner(self, document_id: UUID, owner_id: UUID) -> DocumentRecord | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id),
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return document_record_from_model(model)


def document_record_from_model(model: Document) -> DocumentRecord:
    return DocumentRecord(
        id=model.id,
        owner_id=model.owner_id,
        title=model.title,
        original_filename=model.original_filename,
        content_type=model.content_type,
        file_size_bytes=model.file_size_bytes,
        sha256_hash=model.sha256_hash,
        storage_bucket=model.storage_bucket,
        storage_key=model.storage_key,
        source_kind=DocumentSourceKind(model.source_kind),
        status=DocumentStatus(model.status),
        document_type=model.document_type,
        document_date=model.document_date,
        issuer=model.issuer,
        organization=model.organization,
        processing_error=model.processing_error,
        processing_started_at=model.processing_started_at,
        processing_completed_at=model.processing_completed_at,
        archived_at=model.archived_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
