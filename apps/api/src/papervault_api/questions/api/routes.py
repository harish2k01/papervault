import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.core.model_clients import ModelProviderError
from papervault_api.db.session import get_session
from papervault_api.documents.infrastructure.ai import build_embedding_provider
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.questions.api.schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    QuestionCitationResponse,
)
from papervault_api.questions.application.evidence_analysis import SourceSpanAnswerProvider
from papervault_api.questions.application.hybrid import HybridRetriever
from papervault_api.questions.application.service import QuestionAnsweringService
from papervault_api.questions.infrastructure.local_inference import InferenceUnavailable
from papervault_api.questions.infrastructure.providers import (
    build_grounded_answer_provider,
    refused_answer,
)
from papervault_api.questions.infrastructure.rag_factory import (
    analysis_client,
    pipeline_id,
    semantic_models,
)
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/capabilities")
async def question_capabilities(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    return {"structured_retrieval": settings.rag_mode}


@router.get("/intelligence/{document_id}")
async def candidate_understanding(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == current_user.id)
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    if settings.rag_mode == "disabled":
        return {"status": "disabled"}
    index = await session.scalar(
        select(DocumentRagIndex)
        .join(
            DocumentTextExtraction,
            DocumentTextExtraction.id == DocumentRagIndex.text_extraction_id,
        )
        .where(
            DocumentRagIndex.document_id == document_id,
            DocumentRagIndex.pipeline_id == pipeline_id(settings),
            DocumentTextExtraction.is_current.is_(True),
        )
    )
    if index is None:
        return {"status": "not_indexed"}
    return {
        "status": index.status,
        "page_count": index.page_count,
        "covered_pages": index.covered_pages,
        "warnings": index.warnings,
        "understanding": index.understanding,
        "pipeline_id": index.pipeline_id,
        "embedding_model": index.embedding_model,
    }


@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question(
    request: AskQuestionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskQuestionResponse:
    candidate = request.retrieval == "candidate" or settings.rag_mode == "enabled"
    if candidate:
        if settings.rag_mode == "disabled":
            raise HTTPException(409, "Structured retrieval preview is not enabled")
        settings.validate_private_inference_url(settings.ollama_base_url)
        missing_index = await session.scalar(
            select(Document.id)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.document_id == Document.id,
            )
            .outerjoin(
                DocumentRagIndex,
                and_(
                    DocumentRagIndex.text_extraction_id == DocumentTextExtraction.id,
                    DocumentRagIndex.pipeline_id == pipeline_id(settings),
                ),
            )
            .where(
                Document.owner_id == current_user.id,
                Document.status == "ready",
                Document.archived_at.is_(None),
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == "succeeded",
                or_(DocumentRagIndex.id.is_(None), DocumentRagIndex.status != "ready"),
            )
            .limit(1)
        )
        if missing_index is not None:
            raise HTTPException(
                409,
                "The structured index is incomplete. Check document intelligence status "
                "and retry after indexing finishes.",
            )
        try:
            evidence = await HybridRetriever(
                session,
                semantic_models(settings),
                pipeline_id(settings),
                settings.rag_min_rerank_score,
            ).retrieve(current_user.id, request.question)
            result = await asyncio.to_thread(
                SourceSpanAnswerProvider(analysis_client(settings)).answer,
                request.question,
                evidence,
            )
            # A completed model response must not resurrect replaced/deleted source text.
            for item in evidence:
                still_current = await session.scalar(
                    select(DocumentTextExtraction.id)
                    .join(Document, Document.id == DocumentTextExtraction.document_id)
                    .where(
                        Document.id == item.document_id,
                        Document.owner_id == current_user.id,
                        Document.status == "ready",
                        Document.archived_at.is_(None),
                        DocumentTextExtraction.id == item.text_extraction_id,
                        DocumentTextExtraction.is_current.is_(True),
                    )
                )
                if still_current is None:
                    result = refused_answer("The source changed while answering. Please try again.")
                    break
        except (InferenceUnavailable, ModelProviderError, ValueError):
            raise HTTPException(
                503, "Local document intelligence is unavailable. Your documents remain accessible."
            ) from None
    else:
        result = await QuestionAnsweringService(
            session=session,
            embedding_provider=build_embedding_provider(
                settings.embedding_provider,
                settings.embedding_dimensions,
                settings,
            ),
            answer_provider=build_grounded_answer_provider(settings.answer_provider, settings),
        ).ask(owner_id=current_user.id, question=request.question)
    return AskQuestionResponse(
        answered=result.answered,
        answer=result.answer,
        confidence_score=result.confidence_score,
        citations=[
            QuestionCitationResponse(
                document_id=citation.document_id,
                document_title=citation.document_title,
                original_filename=citation.original_filename,
                page_number=citation.page_number,
                snippet=citation.snippet,
                relevance_score=citation.relevance_score,
            )
            for citation in result.citations
        ],
        refusal_reason=result.refusal_reason,
        answer_kind="source_span" if candidate else "legacy",
    )
