from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.application.uploads import DocumentUploadService
from papervault_api.documents.infrastructure.queues import CeleryDocumentProcessingQueue
from papervault_api.documents.infrastructure.storage import S3ObjectStorage


def get_object_storage(settings: Annotated[Settings, Depends(get_settings)]) -> ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
    )


def get_document_processing_queue() -> DocumentProcessingQueue:
    return CeleryDocumentProcessingQueue()


def get_document_upload_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    queue: Annotated[DocumentProcessingQueue, Depends(get_document_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentUploadService:
    return DocumentUploadService(
        session=session,
        storage=storage,
        processing_queue=queue,
        bucket_name=settings.s3_bucket_documents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
    )
