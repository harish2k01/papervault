from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.search.api.schemas import (
    RecentSearchResponse,
    SavedSearchResponse,
    SaveSearchRequest,
    SearchFiltersRequest,
    SearchRequestBody,
    SearchResponse,
    SearchResultResponse,
)
from papervault_api.search.application.service import (
    DocumentSearchService,
    SearchFilters,
    SearchRequest,
)
from papervault_api.search.domain.enums import SearchMode

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


def filters_from_request(request: SearchFiltersRequest) -> SearchFilters:
    return SearchFilters(
        document_type=request.document_type,
        issuer=request.issuer,
        organization=request.organization,
        tag=request.tag,
        date_from=request.date_from,
        date_to=request.date_to,
    )
