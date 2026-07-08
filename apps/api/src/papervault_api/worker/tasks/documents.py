import asyncio
from uuid import UUID

from papervault_api.core.config import get_settings
from papervault_api.db.session import AsyncSessionFactory
from papervault_api.documents.application.ai import DocumentAIProcessingService
from papervault_api.documents.application.processing import DocumentProcessingService
from papervault_api.documents.infrastructure.ai import (
    build_document_ai_provider,
    build_embedding_provider,
)
from papervault_api.documents.infrastructure.storage import S3ObjectStorage
from papervault_api.documents.infrastructure.text_extractors import build_default_text_extractor
from papervault_api.notifications.application.service import NotificationService
from papervault_api.worker.celery_app import celery_app


@celery_app.task(name="papervault.documents.process_document")  # type: ignore[untyped-decorator]
def process_document(document_id: str) -> str:
    asyncio.run(_process_document(UUID(document_id)))
    return document_id


async def _process_document(document_id: UUID) -> None:
    settings = get_settings()
    storage = S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
    )
    async with AsyncSessionFactory() as session:
        document_processing_service = DocumentProcessingService(
            session=session,
            storage=storage,
            text_extractor=build_default_text_extractor(),
        )
        await document_processing_service.process_document(document_id)

    if not settings.ai_enabled:
        return

    async with AsyncSessionFactory() as session:
        ai_processing_service = DocumentAIProcessingService(
            session=session,
            ai_provider=build_document_ai_provider(settings.ai_provider),
            embedding_provider=build_embedding_provider(
                settings.embedding_provider,
                settings.embedding_dimensions,
            ),
            classification_threshold=settings.ai_classification_threshold,
        )
        await ai_processing_service.process_document(document_id)

    async with AsyncSessionFactory() as session:
        notification_service = NotificationService(session)
        await notification_service.generate_for_document(document_id)
