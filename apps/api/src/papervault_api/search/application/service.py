import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from math import sqrt
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.infrastructure.ai import build_embedding_provider, tokenize
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentEmbedding,
    DocumentTextExtraction,
)
from papervault_api.search.domain.enums import SearchMode
from papervault_api.search.infrastructure.models import RecentSearch, SavedSearch
from papervault_api.tags.infrastructure.models import DocumentTag, Tag

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SearchFilters:
    document_type: str | None = None
    issuer: str | None = None
    organization: str | None = None
    tag: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    include_archived: bool = False

    def as_dict(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if self.document_type:
            values["document_type"] = self.document_type
        if self.issuer:
            values["issuer"] = self.issuer
        if self.organization:
            values["organization"] = self.organization
        if self.tag:
            values["tag"] = self.tag
        if self.date_from:
            values["date_from"] = self.date_from.isoformat()
        if self.date_to:
            values["date_to"] = self.date_to.isoformat()
        if self.include_archived:
            values["include_archived"] = "true"
        return values


@dataclass(frozen=True, slots=True)
class SearchRequest:
    owner_id: UUID
    query: str = ""
    mode: SearchMode = SearchMode.HYBRID
    filters: SearchFilters = field(default_factory=SearchFilters)
    limit: int = 25
    offset: int = 0
    record_recent: bool = True


@dataclass(frozen=True, slots=True)
class SearchResult:
    document_id: UUID
    title: str
    original_filename: str
    document_type: str
    status: str
    summary: str | None
    created_at: datetime
    score: float
    highlights: tuple[str, ...]


class SearchQueryIndex(Protocol):
    def search(
        self,
        request: SearchRequest,
        query_embedding: tuple[float, ...] | None,
    ) -> tuple[SearchResult, ...]:
        raise NotImplementedError


class DocumentSearchService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        embedding_provider_name: str,
        embedding_dimensions: int,
        settings: Settings | None = None,
        search_query_index: SearchQueryIndex | None = None,
        query_fallback_enabled: bool = True,
    ) -> None:
        self._session = session
        self._embedding_provider_name = embedding_provider_name
        self._embedding_dimensions = embedding_dimensions
        self._settings = settings
        self._search_query_index = search_query_index
        self._query_fallback_enabled = query_fallback_enabled

    async def search(self, request: SearchRequest) -> tuple[SearchResult, ...]:
        query_embedding = await self._build_query_embedding(request)
        if request.record_recent:
            await self._record_recent_search(request)

        if self._search_query_index is not None:
            try:
                results = await asyncio.to_thread(
                    self._search_query_index.search,
                    request,
                    query_embedding,
                )
                await self._session.commit()
                return results
            except Exception as exc:
                if not self._query_fallback_enabled:
                    await self._session.rollback()
                    raise
                logger.warning(
                    "search_query_index_failed_falling_back",
                    owner_id=str(request.owner_id),
                    mode=request.mode.value,
                    error=str(exc),
                )

        results = await self._search_database(request, query_embedding)
        await self._session.commit()
        return results

    async def _record_recent_search(self, request: SearchRequest) -> None:
        latest = await self._session.scalar(
            select(RecentSearch)
            .where(RecentSearch.owner_id == request.owner_id)
            .order_by(RecentSearch.searched_at.desc())
            .limit(1),
        )
        filters = request.filters.as_dict()
        if (
            latest is not None
            and latest.query == request.query
            and latest.mode == request.mode.value
            and latest.filters == filters
        ):
            return
        self._session.add(
            RecentSearch(
                owner_id=request.owner_id,
                query=request.query,
                mode=request.mode.value,
                filters=filters,
            ),
        )
        await self._session.flush()

    async def _build_query_embedding(
        self,
        request: SearchRequest,
    ) -> tuple[float, ...] | None:
        if not request.query or request.mode not in {SearchMode.SEMANTIC, SearchMode.HYBRID}:
            return None
        provider = build_embedding_provider(
            self._embedding_provider_name,
            self._embedding_dimensions,
            self._settings,
        )
        embedding = await asyncio.to_thread(provider.embed, request.query)
        return embedding.vector

    async def _search_database(
        self,
        request: SearchRequest,
        query_embedding: tuple[float, ...] | None,
    ) -> tuple[SearchResult, ...]:
        documents = await self._load_candidate_documents(request)
        text_by_document = await self._load_current_text(documents)
        embedding_by_document = await self._load_current_embeddings(documents)

        scored: list[SearchResult] = []
        for document in documents:
            searchable_text = " ".join(
                value
                for value in (
                    document.title,
                    document.original_filename,
                    document.issuer,
                    document.organization,
                    document.summary,
                    text_by_document.get(document.id),
                )
                if value
            )
            keyword_score = score_keyword(request.query, searchable_text)
            semantic_score = 0.0
            if query_embedding is not None:
                embedding = embedding_by_document.get(document.id)
                if embedding is not None:
                    semantic_score = cosine_similarity(query_embedding, tuple(embedding.vector))

            score = combine_scores(request.mode, keyword_score, semantic_score)
            if request.query and score == 0:
                continue

            scored.append(
                SearchResult(
                    document_id=document.id,
                    title=document.title,
                    original_filename=document.original_filename,
                    document_type=document.document_type,
                    status=document.status,
                    summary=document.summary,
                    created_at=document.created_at,
                    score=round(score, 6),
                    highlights=build_highlights(request.query, searchable_text),
                ),
            )

        scored.sort(key=lambda result: (result.score, result.created_at), reverse=True)
        return tuple(scored[request.offset : request.offset + request.limit])

    async def save_search(
        self,
        *,
        owner_id: UUID,
        name: str,
        query: str,
        mode: SearchMode,
        filters: SearchFilters,
    ) -> SavedSearch:
        saved_search = SavedSearch(
            owner_id=owner_id,
            name=name,
            query=query,
            mode=mode.value,
            filters=filters.as_dict(),
        )
        self._session.add(saved_search)
        await self._session.commit()
        await self._session.refresh(saved_search)
        return saved_search

    async def list_saved_searches(self, owner_id: UUID) -> tuple[SavedSearch, ...]:
        result = await self._session.execute(
            select(SavedSearch)
            .where(SavedSearch.owner_id == owner_id)
            .order_by(SavedSearch.created_at.desc()),
        )
        return tuple(result.scalars())

    async def list_recent_searches(
        self, owner_id: UUID, limit: int = 10
    ) -> tuple[RecentSearch, ...]:
        result = await self._session.execute(
            select(RecentSearch)
            .where(RecentSearch.owner_id == owner_id)
            .order_by(RecentSearch.searched_at.desc())
            .limit(limit),
        )
        return tuple(result.scalars())

    async def _load_candidate_documents(self, request: SearchRequest) -> list[Document]:
        statement = select(Document).where(Document.owner_id == request.owner_id)
        statement = apply_filters(statement, request.filters)

        if request.filters.tag:
            statement = (
                statement.join(DocumentTag, DocumentTag.document_id == Document.id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(Tag.slug == request.filters.tag)
            )

        result = await self._session.execute(
            statement.order_by(Document.created_at.desc()).limit(500)
        )
        return list(result.scalars().unique())

    async def _load_current_text(self, documents: list[Document]) -> dict[UUID, str]:
        document_ids = [document.id for document in documents]
        if not document_ids:
            return {}

        result = await self._session.execute(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id.in_(document_ids),
                DocumentTextExtraction.is_current.is_(True),
            ),
        )
        return {
            extraction.document_id: extraction.content_text or "" for extraction in result.scalars()
        }

    async def _load_current_embeddings(
        self, documents: list[Document]
    ) -> dict[UUID, DocumentEmbedding]:
        document_ids = [document.id for document in documents]
        if not document_ids:
            return {}

        result = await self._session.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.document_id.in_(document_ids),
                DocumentEmbedding.is_current.is_(True),
            ),
        )
        return {embedding.document_id: embedding for embedding in result.scalars()}


def apply_filters(
    statement: Select[tuple[Document]], filters: SearchFilters
) -> Select[tuple[Document]]:
    clauses = []
    if not filters.include_archived:
        clauses.append(Document.status != DocumentStatus.ARCHIVED.value)
    if filters.document_type:
        clauses.append(Document.document_type == filters.document_type)
    if filters.issuer:
        clauses.append(func.lower(Document.issuer) == filters.issuer.lower())
    if filters.organization:
        clauses.append(func.lower(Document.organization) == filters.organization.lower())
    if filters.date_from:
        clauses.append(Document.document_date >= filters.date_from)
    if filters.date_to:
        clauses.append(Document.document_date <= filters.date_to)
    if clauses:
        return statement.where(and_(*clauses))
    return statement


def score_keyword(query: str, text: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    text_tokens = tokenize(text)
    if not text_tokens:
        return 0.0

    text_token_set = set(text_tokens)
    matches = sum(1 for token in query_tokens if token in text_token_set)
    return matches / len(query_tokens)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def combine_scores(mode: SearchMode, keyword_score: float, semantic_score: float) -> float:
    if mode is SearchMode.KEYWORD:
        return keyword_score
    if mode is SearchMode.SEMANTIC:
        return semantic_score
    return (keyword_score * 0.55) + (semantic_score * 0.45)


def build_highlights(query: str, text: str, limit: int = 3) -> tuple[str, ...]:
    if not query:
        return ()
    lower_text = text.lower()
    highlights: list[str] = []
    for token in tokenize(query):
        position = lower_text.find(token)
        if position == -1:
            continue
        start = max(0, position - 60)
        end = min(len(text), position + len(token) + 60)
        highlights.append(text[start:end].strip())
        if len(highlights) >= limit:
            break
    return tuple(highlights)
