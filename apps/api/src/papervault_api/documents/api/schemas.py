from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from papervault_api.documents.domain.enums import DocumentSourceKind, DocumentStatus


class DocumentResponse(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    sha256_hash: str
    source_kind: DocumentSourceKind
    status: DocumentStatus
    document_type: str
    created_at: datetime
    updated_at: datetime


class UploadDocumentResponse(BaseModel):
    document: DocumentResponse
    processing_task_id: str | None


class DocumentTagResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    color: str | None


class TimelineEventResponse(BaseModel):
    id: UUID
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class AIAnalysisResponse(BaseModel):
    summary: str | None
    keywords: list[str]
    entities: list[dict[str, Any]]
    suggested_tags: list[str]
    category: str | None
    confidence_score: float | None


class MetadataResponse(BaseModel):
    schema_name: str
    schema_version: int
    data: dict[str, Any]
    confidence_score: float | None


class TextExtractionResponse(BaseModel):
    status: str
    source: str
    page_count: int | None
    language: str | None
    error_message: str | None


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    ai_analysis: AIAnalysisResponse | None
    metadata: MetadataResponse | None
    text_extraction: TextExtractionResponse | None
    tags: list[DocumentTagResponse]
    timeline_events: list[TimelineEventResponse]


class DuplicateCandidateDocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    sha256_hash: str
    created_at: datetime


class DuplicateCandidateGroupResponse(BaseModel):
    method: str
    documents: list[DuplicateCandidateDocumentResponse]
