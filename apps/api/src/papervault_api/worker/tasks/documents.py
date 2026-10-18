import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select

from papervault_api.core.config import get_settings
from papervault_api.db import models as _models  # noqa: F401
from papervault_api.db.session import AsyncSessionFactory, engine
from papervault_api.documents.application.ai import DocumentAIProcessingService
from papervault_api.documents.application.duplicates import DuplicateDetectionService
from papervault_api.documents.application.processing import (
    DocumentProcessingService,
    mark_document_processing_failed,
)
from papervault_api.documents.domain.enums import DocumentReviewStatus, DocumentStatus
from papervault_api.documents.infrastructure.ai import (
    build_document_ai_provider,
    build_embedding_provider,
)
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.documents.infrastructure.storage import S3ObjectStorage
from papervault_api.documents.infrastructure.text_extractors import build_default_text_extractor
from papervault_api.notifications.application.service import NotificationService
from papervault_api.search.application.indexing import SearchIndexingService
from papervault_api.search.infrastructure.opensearch import build_search_document_index
from papervault_api.tags.application.service import TagService
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
        document = await session.get(Document, document_id)
        if document is None or document.status != DocumentStatus.READY.value:
            return

        extraction_id = await session.scalar(
            select(DocumentTextExtraction.id).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == "succeeded",
            )
        )

    await _refresh_duplicate_fingerprint(document_id)
    await _refresh_notifications(document_id)
    await _index_document(document_id)
    if extraction_id is None:
        await _mark_enrichment_failed(document_id)
        return
    if settings.rag_mode != "disabled":
        try:
            celery_app.send_task(
                "papervault.rag.index",
                args=[str(document_id), str(extraction_id)],
                queue="papervault-index",
            )
        except Exception:
            logger.warning("candidate_index_queue_failed")
    if settings.ai_enabled and settings.enrichment_queue_enabled:
        try:
            celery_app.send_task(
                "papervault.documents.enrich_document",
                args=[str(document_id), str(extraction_id)],
                queue="papervault-enrichment",
            )
        except Exception:
            await _mark_enrichment_failed(document_id, extraction_id)
            logger.exception("document_enrichment_queue_failed", document_id=str(document_id))
        return
    await _enrich_document(document_id, extraction_id)


@celery_app.task(
    name="papervault.documents.enrich_document",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)  # type: ignore[untyped-decorator]
def enrich_document(document_id: str, extraction_id: str) -> str:
    asyncio.run(_run_enrichment_task(UUID(document_id), UUID(extraction_id)))
    return document_id


async def _run_enrichment_task(document_id: UUID, extraction_id: UUID) -> None:
    try:
        await _enrich_document(document_id, extraction_id)
    finally:
        await engine.dispose()


async def _mark_enrichment_failed(document_id: UUID, extraction_id: UUID | None = None) -> None:
    async with AsyncSessionFactory() as session:
        document = await session.get(Document, document_id)
        if extraction_id is not None:
            current = await session.scalar(
                select(DocumentTextExtraction.id).where(
                    DocumentTextExtraction.document_id == document_id,
                    DocumentTextExtraction.is_current.is_(True),
                )
            )
            if current != extraction_id:
                return
        if document is not None and document.status == DocumentStatus.READY.value:
            document.review_status = DocumentReviewStatus.PENDING.value
            document.review_reasons = list(
                dict.fromkeys(
                    [
                        reason
                        for reason in document.review_reasons
                        if reason != "analysis_pending:metadata"
                    ]
                    + ["analysis_failed:metadata"]
                )
            )
            await session.commit()


async def _enrich_document(document_id: UUID, extraction_id: UUID | None = None) -> None:
    settings = get_settings()
    if settings.ai_enabled:
        try:
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
                    metadata_locale=settings.metadata_locale,
                )
                processed = await ai_processing_service.process_document(
                    document_id, expected_extraction_id=extraction_id
                )
                if not processed:
                    return
        except Exception:
            logger.exception(
                "document_enrichment_failed_text_preserved",
                document_id=str(document_id),
            )
            await _mark_enrichment_failed(document_id, extraction_id)

    else:
        async with AsyncSessionFactory() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.review_reasons = [
                    reason
                    for reason in document.review_reasons
                    if reason != "analysis_pending:metadata"
                ] + ["analysis_disabled:metadata"]
                await session.commit()

    await _sync_smart_tags(document_id)

    await _refresh_notifications(document_id)
    await _index_document(document_id)


async def _refresh_notifications(document_id: UUID) -> None:
    try:
        async with AsyncSessionFactory() as session:
            await NotificationService(session).generate_for_document(document_id)
    except Exception:
        logger.exception("document_notification_refresh_failed", document_id=str(document_id))


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


async def _refresh_duplicate_fingerprint(document_id: UUID) -> None:
    settings = get_settings()
    try:
        async with AsyncSessionFactory() as session:
            await DuplicateDetectionService(
                session,
                content_similarity_threshold=(settings.duplicate_content_similarity_threshold),
                ocr_similarity_threshold=settings.duplicate_ocr_similarity_threshold,
                min_tokens=settings.duplicate_similarity_min_tokens,
            ).refresh_document(document_id)
    except Exception:
        logger.exception(
            "document_duplicate_fingerprint_failed",
            document_id=str(document_id),
        )


async def _sync_smart_tags(document_id: UUID) -> None:
    try:
        async with AsyncSessionFactory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                return
            await TagService(session).synchronize_document(
                owner_id=document.owner_id,
                document_id=document_id,
                actor_id=None,
            )
    except Exception:
        logger.exception(
            "document_smart_tag_sync_failed",
            document_id=str(document_id),
        )
