from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from papervault_api.search.domain.enums import SearchMode


class SearchFiltersRequest(BaseModel):
    document_type: str | None = None
    issuer: str | None = None
    organization: str | None = None
    tag: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    include_archived: bool = False


class SearchRequestBody(BaseModel):
    query: str = ""
    mode: SearchMode = SearchMode.HYBRID
    filters: SearchFiltersRequest = Field(default_factory=SearchFiltersRequest)
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResultResponse(BaseModel):
    document_id: UUID
    title: str
    original_filename: str
    document_type: str
    status: str
    summary: str | None
    created_at: datetime
    score: float
    highlights: list[str]


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]


class SaveSearchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = ""
    mode: SearchMode = SearchMode.HYBRID
    filters: SearchFiltersRequest = Field(default_factory=SearchFiltersRequest)


class SavedSearchResponse(BaseModel):
    id: UUID
    name: str
    query: str
    mode: SearchMode
    filters: dict[str, Any]
    created_at: datetime


class RecentSearchResponse(BaseModel):
    id: UUID
    query: str
    mode: SearchMode
    filters: dict[str, Any]
    searched_at: datetime


class SearchIndexDocumentResponse(BaseModel):
    document_id: UUID
    indexed: bool


class SearchIndexRebuildResponse(BaseModel):
    requested_limit: int
    indexed_count: int
