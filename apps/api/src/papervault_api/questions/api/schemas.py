from uuid import UUID

from pydantic import BaseModel, Field


class AskQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class QuestionCitationResponse(BaseModel):
    document_id: UUID
    document_title: str
    original_filename: str
    page_number: int
    snippet: str
    relevance_score: float


class AskQuestionResponse(BaseModel):
    answered: bool
    answer: str | None
    confidence_score: float
    citations: list[QuestionCitationResponse]
    refusal_reason: str | None
