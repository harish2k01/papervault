from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

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
    document_date: date | None
    issuer: str | None
    organization: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UploadDocumentResponse(BaseModel):
    document: DocumentResponse
    processing_task_id: str | None


class MetadataFieldDefinitionResponse(BaseModel):
    key: str
    label: str
    field_type: str
    required: bool


class DocumentTypeResponse(BaseModel):
    key: str
    label: str
    metadata_fields: list[MetadataFieldDefinitionResponse]


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


class DocumentVersionResponse(BaseModel):
    id: UUID
    version_number: int
    sha256_hash: str
    file_size_bytes: int
    change_reason: str | None
    created_by_id: UUID | None
    created_at: datetime


class TextExtractionResponse(BaseModel):
    status: str
    source: str
    page_count: int | None
    language: str | None
    error_message: str | None


class DocumentTextMatchResponse(BaseModel):
    page_number: int | None
    before: str
    match: str
    after: str


class DocumentTextSearchResponse(BaseModel):
    query: str
    total_matches: int
    matches: list[DocumentTextMatchResponse]
    page_mapping_available: bool


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    ai_analysis: AIAnalysisResponse | None
    metadata: MetadataResponse | None
    text_extraction: TextExtractionResponse | None
    tags: list[DocumentTagResponse]
    timeline_events: list[TimelineEventResponse]
    versions: list[DocumentVersionResponse]


class UpdateDocumentRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    document_type: str | None = Field(default=None, min_length=1, max_length=80)
    document_date: date | None = None
    issuer: str | None = Field(default=None, max_length=255)
    organization: str | None = Field(default=None, max_length=255)


class UpdateMetadataRequest(BaseModel):
    schema_name: str | None = Field(default=None, min_length=1, max_length=80)
    data: dict[str, Any] = Field(default_factory=dict)
    document_date: date | None = None
    issuer: str | None = Field(default=None, max_length=255)
    organization: str | None = Field(default=None, max_length=255)


class DuplicateCandidateDocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    sha256_hash: str
    created_at: datetime


class DuplicateCandidateGroupResponse(BaseModel):
    method: str
    documents: list[DuplicateCandidateDocumentResponse]


class MergeDuplicateDocumentsRequest(BaseModel):
    keep_document_id: UUID
    duplicate_document_ids: list[UUID] = Field(min_length=1)


class MergeDuplicateDocumentsResponse(BaseModel):
    kept_document: DocumentResponse
    archived_documents: list[DocumentResponse]
