import asyncio
from uuid import UUID

import structlog

from papervault_api.core.config import get_settings
from papervault_api.db import models as _models  # noqa: F401
from papervault_api.db.session import AsyncSessionFactory, engine
from papervault_api.documents.application.ai import DocumentAIProcessingService
from papervault_api.documents.application.processing import (
    DocumentProcessingService,
    mark_document_processing_failed,
)
from papervault_api.documents.infrastructure.ai import (
    build_document_ai_provider,
    build_embedding_provider,
)
from papervault_api.documents.infrastructure.storage import S3ObjectStorage
from papervault_api.documents.infrastructure.text_extractors import build_default_text_extractor
from papervault_api.notifications.application.service import NotificationService
from papervault_api.search.application.indexing import SearchIndexingService
from papervault_api.search.infrastructure.opensearch import build_search_document_index
from papervault_api.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="papervault.documents.process_document")  # type: ignore[untyped-decorator]
def process_document(document_id: str) -> str:
    asyncio.run(_run_process_document_task(UUID(document_id)))
    return document_id


async def _run_process_document_task(document_id: UUID) -> None:
    try:
        await _process_document(document_id)
    except Exception as exc:
        logger.exception(
            "document_processing_failed",
            document_id=str(document_id),
            error_type=type(exc).__name__,
        )
        try:
            async with AsyncSessionFactory() as session:
                await mark_document_processing_failed(
                    session,
                    document_id,
                    message=(
                        "Document processing failed unexpectedly. Retry the document or "
                        "inspect the worker logs."
                    ),
                )
        except Exception:
            logger.exception(
                "document_processing_failure_status_update_failed",
                document_id=str(document_id),
            )
        raise
    finally:
        await engine.dispose()


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
            text_extractor=build_default_text_extractor(settings),
        )
        await document_processing_service.process_document(document_id)

    if settings.ai_enabled:
        async with AsyncSessionFactory() as session:
            ai_processing_service = DocumentAIProcessingService(
                session=session,
                ai_provider=build_document_ai_provider(settings.ai_provider, settings),
                embedding_provider=build_embedding_provider(
                    settings.embedding_provider,
                    settings.embedding_dimensions,
                    settings,
                ),
                classification_threshold=settings.ai_classification_threshold,
            )
            await ai_processing_service.process_document(document_id)

    async with AsyncSessionFactory() as session:
        notification_service = NotificationService(session)
        await notification_service.generate_for_document(document_id)

    await _index_document(document_id)


async def _index_document(document_id: UUID) -> None:
    settings = get_settings()
    if not settings.search_index_enabled:
        return

    try:
        async with AsyncSessionFactory() as session:
            search_indexing_service = SearchIndexingService(
                session=session,
                search_index=build_search_document_index(settings),
            )
            await search_indexing_service.index_document(document_id)
    except Exception:
        logger.exception(
            "document_search_indexing_failed",
            document_id=str(document_id),
        )
