import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select

from papervault_api.core.config import get_settings
from papervault_api.db.session import AsyncSessionFactory, engine
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.documents.infrastructure.storage import S3ObjectStorage
from papervault_api.questions.application.evidence_analysis import extract_findings
from papervault_api.questions.application.indexing import StructuredIndexingService
from papervault_api.questions.infrastructure.local_inference import LayoutParser, PrivateInference
from papervault_api.questions.infrastructure.rag_factory import (
    analysis_client,
    pipeline_id,
    semantic_models,
)
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex, DocumentRagPassage
from papervault_api.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="papervault.rag.index",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    max_retries=2,
)  # type: ignore[untyped-decorator]
def index_document(document_id: str, extraction_id: str) -> str:
    asyncio.run(_index(UUID(document_id), UUID(extraction_id)))
    return document_id


async def _index(document_id: UUID, extraction_id: UUID) -> None:
    settings = get_settings()
    if settings.rag_mode == "disabled":
        return
    try:
        await _record_index_state(document_id, extraction_id, "building")
        async with AsyncSessionFactory() as session:
            await StructuredIndexingService(
                session,
                S3ObjectStorage(
                    endpoint_url=settings.s3_endpoint_url,
                    access_key_id=settings.s3_access_key_id,
                    secret_access_key=settings.s3_secret_access_key,
                    region=settings.s3_region,
                ),
                LayoutParser(PrivateInference(settings.rag_parser_url, 1200)),
                semantic_models(settings),
                pipeline_id(settings),
            ).build(document_id, extraction_id)
            index_id = await session.scalar(
                select(DocumentRagIndex.id).where(
                    DocumentRagIndex.document_id == document_id,
                    DocumentRagIndex.text_extraction_id == extraction_id,
                    DocumentRagIndex.pipeline_id == pipeline_id(settings),
                    DocumentRagIndex.status == "ready",
                )
            )
        if index_id is not None:
            celery_app.send_task(
                "papervault.rag.understand", args=[str(index_id)], queue="papervault-understanding"
            )
    except Exception as exc:
        # No raw exception traceback: providers can include source data in errors.
        logger.warning("candidate_index_failed", error_type=type(exc).__name__)
        await _record_index_state(document_id, extraction_id, "failed")
        raise RuntimeError("Candidate index could not be built") from None
    finally:
        await engine.dispose()


async def _record_index_state(document_id: UUID, extraction_id: UUID, status: str) -> None:
    settings = get_settings()
    async with AsyncSessionFactory() as session:
        document = await session.scalar(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        source = await session.scalar(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.id == extraction_id,
                DocumentTextExtraction.is_current.is_(True),
            )
        )
        if document is None or source is None:
            return
        index = await session.scalar(
            select(DocumentRagIndex).where(
                DocumentRagIndex.text_extraction_id == extraction_id,
                DocumentRagIndex.pipeline_id == pipeline_id(settings),
            )
        )
        if index is not None and index.status == "ready":
            return
        if index is None:
            index = DocumentRagIndex(
                document_id=document_id,
                text_extraction_id=extraction_id,
                pipeline_id=pipeline_id(settings),
                parser_model=LayoutParser.identity,
                embedding_model=settings.rag_embedding_model,
                embedding_revision=settings.rag_embedding_revision,
                dimensions=settings.rag_dimensions,
                page_count=source.page_count or 0,
                covered_pages=[],
                understanding={},
            )
            session.add(index)
        index.status = status
        index.warnings = ["structured_index_failed"] if status == "failed" else []
        await session.commit()


@celery_app.task(
    name="papervault.rag.understand",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    max_retries=2,
)  # type: ignore[untyped-decorator]
def understand_document(index_id: str) -> str:
    asyncio.run(_understand(UUID(index_id)))
    return index_id


async def _understand(index_id: UUID) -> None:
    settings = get_settings()
    if settings.rag_mode == "disabled":
        return
    settings.validate_private_inference_url(settings.ollama_base_url)
    try:
        async with AsyncSessionFactory() as session:
            index = await session.scalar(
                select(DocumentRagIndex)
                .join(
                    DocumentTextExtraction,
                    DocumentTextExtraction.id == DocumentRagIndex.text_extraction_id,
                )
                .join(Document, Document.id == DocumentRagIndex.document_id)
                .where(
                    DocumentRagIndex.id == index_id,
                    DocumentRagIndex.pipeline_id == pipeline_id(settings),
                    DocumentRagIndex.status == "ready",
                    DocumentTextExtraction.is_current.is_(True),
                    Document.status == "ready",
                )
            )
            model = settings.rag_chat_model or settings.ollama_chat_model
            digest = settings.rag_chat_digest or settings.ollama_expected_digest
            if index is None or (
                index.understanding.get("status") == "needs_review"
                and index.understanding.get("model") == model
                and index.understanding.get("model_digest") == digest
            ):
                return
            index.understanding = {"status": "processing", "model": model, "model_digest": digest}
            await session.commit()
            passages = list(
                (
                    await session.scalars(
                        select(DocumentRagPassage)
                        .where(
                            DocumentRagPassage.index_id == index_id,
                        )
                        .order_by(DocumentRagPassage.ordinal)
                    )
                ).all()
            )
            result = await asyncio.to_thread(
                extract_findings,
                analysis_client(settings),
                [
                    {
                        "ordinal": passage.ordinal,
                        "page_number": passage.page_number,
                        "section": passage.section,
                        "text": passage.content_text,
                    }
                    for passage in passages
                ],
            )
            result.update(
                {"model": model, "model_digest": digest, "prompt_version": "source-findings-v1"}
            )
            current = await session.scalar(
                select(DocumentTextExtraction.id).where(
                    DocumentTextExtraction.id == index.text_extraction_id,
                    DocumentTextExtraction.is_current.is_(True),
                )
            )
            fresh = await session.get(DocumentRagIndex, index_id, populate_existing=True)
            if current is not None and fresh is not None:
                fresh.understanding = result
                await session.commit()
    except Exception as exc:
        logger.warning("candidate_understanding_failed", error_type=type(exc).__name__)
        async with AsyncSessionFactory() as session:
            failed = await session.get(DocumentRagIndex, index_id)
            if failed is not None and failed.understanding.get("status") == "processing":
                failed.understanding = {"status": "failed", "error": "local_analysis_failed"}
                await session.commit()
        raise RuntimeError("Candidate understanding could not be completed") from None
    finally:
        await engine.dispose()
