from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from papervault_api.documents.api.rule_schemas import DocumentRuleRequest


class CreateTagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    color: str | None = Field(default=None, max_length=20)


class TagResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    color: str | None
    source: str
    document_count: int
    smart_rule: DocumentRuleRequest | None
    last_evaluated_at: datetime | None
    created_at: datetime


class TagAssignmentResponse(BaseModel):
    attached: bool


class CreateSmartTagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    color: str | None = Field(default=None, max_length=20)
    rule: DocumentRuleRequest


class UpdateSmartTagRuleRequest(BaseModel):
    rule: DocumentRuleRequest


class SmartTagRefreshResponse(BaseModel):
    evaluated: int
    matched: int
    attached: int
    detached: int
