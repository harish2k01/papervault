from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.infrastructure.models import Document
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.search.api.schemas import (
    RecentSearchResponse,
    SavedSearchResponse,
    SaveSearchRequest,
    SearchFiltersRequest,
    SearchIndexDocumentResponse,
    SearchIndexRebuildResponse,
    SearchRequestBody,
    SearchResponse,
    SearchResultResponse,
)
from papervault_api.search.application.indexing import SearchIndexingService
from papervault_api.search.application.service import (
    DocumentSearchService,
    SearchFilters,
    SearchRequest,
)
from papervault_api.search.domain.enums import SearchMode
from papervault_api.search.infrastructure.opensearch import (
    OpenSearchError,
    build_search_document_index,
    build_search_query_index,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_documents(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: SearchRequestBody,
) -> SearchResponse:
    service = DocumentSearchService(
        session=session,
        embedding_provider_name=settings.embedding_provider,
        embedding_dimensions=settings.embedding_dimensions,
        search_query_index=build_search_query_index(settings),
        query_fallback_enabled=settings.search_query_fallback_enabled,
    )
    results = await service.search(
        SearchRequest(
            owner_id=current_user.id,
            query=request.query,
            mode=request.mode,
            filters=filters_from_request(request.filters),
            limit=request.limit,
            offset=request.offset,
        ),
    )
    return SearchResponse(
        results=[
            SearchResultResponse(
                document_id=result.document_id,
                title=result.title,
                original_filename=result.original_filename,
                document_type=result.document_type,
                status=result.status,
                summary=result.summary,
                created_at=result.created_at,
                score=result.score,
                highlights=list(result.highlights),
            )
            for result in results
        ],
    )


@router.post("/saved", response_model=SavedSearchResponse)
async def save_search(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: SaveSearchRequest,
) -> SavedSearchResponse:
    service = DocumentSearchService(
        session=session,
        embedding_provider_name=settings.embedding_provider,
        embedding_dimensions=settings.embedding_dimensions,
    )
    saved_search = await service.save_search(
        owner_id=current_user.id,
        name=request.name,
        query=request.query,
        mode=request.mode,
        filters=filters_from_request(request.filters),
    )
    return SavedSearchResponse(
        id=saved_search.id,
        name=saved_search.name,
        query=saved_search.query,
        mode=SearchMode(saved_search.mode),
        filters=saved_search.filters,
        created_at=saved_search.created_at,
    )


@router.get("/saved", response_model=list[SavedSearchResponse])
async def list_saved_searches(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SavedSearchResponse]:
    service = DocumentSearchService(
        session=session,
        embedding_provider_name=settings.embedding_provider,
        embedding_dimensions=settings.embedding_dimensions,
    )
    saved_searches = await service.list_saved_searches(current_user.id)
    return [
        SavedSearchResponse(
            id=saved_search.id,
            name=saved_search.name,
            query=saved_search.query,
            mode=SearchMode(saved_search.mode),
            filters=saved_search.filters,
            created_at=saved_search.created_at,
        )
        for saved_search in saved_searches
    ]


@router.get("/recent", response_model=list[RecentSearchResponse])
async def list_recent_searches(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[RecentSearchResponse]:
    service = DocumentSearchService(
        session=session,
        embedding_provider_name=settings.embedding_provider,
        embedding_dimensions=settings.embedding_dimensions,
    )
    recent_searches = await service.list_recent_searches(current_user.id)
    return [
        RecentSearchResponse(
            id=recent_search.id,
            query=recent_search.query,
            mode=SearchMode(recent_search.mode),
            filters=recent_search.filters,
            searched_at=recent_search.searched_at,
        )
        for recent_search in recent_searches
    ]


@router.post("/index/documents/{document_id}", response_model=SearchIndexDocumentResponse)
async def reindex_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchIndexDocumentResponse:
    document = await session.get(Document, document_id)
    if document is None or document.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    service = SearchIndexingService(
        session=session,
        search_index=build_search_document_index(settings),
    )
    try:
        indexed = await service.index_document(document.id)
    except OpenSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return SearchIndexDocumentResponse(document_id=document.id, indexed=indexed)


@router.post("/index/rebuild", response_model=SearchIndexRebuildResponse)
async def rebuild_search_index(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = 500,
) -> SearchIndexRebuildResponse:
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 1000",
        )

    service = SearchIndexingService(
        session=session,
        search_index=build_search_document_index(settings),
    )
    try:
        indexed_count = await service.index_owner_documents(current_user.id, limit=limit)
    except OpenSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return SearchIndexRebuildResponse(
        requested_limit=limit,
        indexed_count=indexed_count,
    )


def filters_from_request(request: SearchFiltersRequest) -> SearchFilters:
    return SearchFilters(
        document_type=request.document_type,
        issuer=request.issuer,
        organization=request.organization,
        tag=request.tag,
        date_from=request.date_from,
        date_to=request.date_to,
        include_archived=request.include_archived,
    )
