from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
    created_at: datetime


class TagAssignmentResponse(BaseModel):
    attached: bool
