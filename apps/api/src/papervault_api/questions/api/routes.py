from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.infrastructure.ai import build_embedding_provider
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.questions.api.schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    QuestionCitationResponse,
)
from papervault_api.questions.application.service import (
    LocalExtractiveAnswerProvider,
    QuestionAnsweringService,
)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question(
    request: AskQuestionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskQuestionResponse:
    result = await QuestionAnsweringService(
        session=session,
        embedding_provider=build_embedding_provider(
            settings.embedding_provider,
            settings.embedding_dimensions,
        ),
        answer_provider=LocalExtractiveAnswerProvider(),
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
    )
