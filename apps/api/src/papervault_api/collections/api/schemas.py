from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from papervault_api.collections.domain.enums import CollectionKind, CollectionView
from papervault_api.documents.api.rule_schemas import DocumentRuleRequest


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    kind: CollectionKind = CollectionKind.MANUAL
    view_mode: CollectionView = CollectionView.GRID
    rule: DocumentRuleRequest = Field(default_factory=DocumentRuleRequest)


class UpdateCollectionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=20)
    view_mode: CollectionView | None = None
    rule: DocumentRuleRequest | None = None


class CollectionResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    color: str | None
    kind: CollectionKind
    view_mode: CollectionView
    rule: DocumentRuleRequest
    document_count: int
    created_at: datetime
    updated_at: datetime


class CollectionDocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    document_type: str
    document_date: date | None
    issuer: str | None
    organization: str | None
    status: str
    file_size_bytes: int
    created_at: datetime


class CollectionDocumentPageResponse(BaseModel):
    documents: list[CollectionDocumentResponse]
    total: int


class CollectionMembershipResponse(BaseModel):
    changed: bool
