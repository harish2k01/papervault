from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.collections.api.schemas import (
    CollectionDocumentPageResponse,
    CollectionDocumentResponse,
    CollectionMembershipResponse,
    CollectionResponse,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from papervault_api.collections.application.service import (
    CollectionConflictError,
    CollectionService,
    CollectionSummary,
    InvalidCollectionOperationError,
)
from papervault_api.collections.domain.enums import CollectionKind, CollectionView
from papervault_api.db.session import get_session
from papervault_api.documents.api.rule_schemas import DocumentRuleRequest
from papervault_api.documents.domain.rules import DocumentRule, InvalidDocumentRuleError
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CollectionResponse]:
    summaries = await CollectionService(session).list_collections(current_user.id)
    return [collection_response(summary) for summary in summaries]


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    request: CreateCollectionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    try:
        summary = await CollectionService(session).create_collection(
            owner_id=current_user.id,
            actor_id=current_user.id,
            name=request.name,
            description=request.description,
            color=request.color,
            kind=request.kind,
            view_mode=request.view_mode,
            rule=document_rule(request.rule),
        )
    except CollectionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidCollectionOperationError, InvalidDocumentRuleError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return collection_response(summary)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    request: UpdateCollectionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    updates = request.model_dump(exclude_unset=True, mode="json")
    try:
        summary = await CollectionService(session).update_collection(
            owner_id=current_user.id,
            actor_id=current_user.id,
            collection_id=collection_id,
            updates=updates,
        )
    except CollectionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidCollectionOperationError, InvalidDocumentRuleError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection_response(summary)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    deleted = await CollectionService(session).delete_collection(
        owner_id=current_user.id,
        actor_id=current_user.id,
        collection_id=collection_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")


@router.get(
    "/{collection_id}/documents",
    response_model=CollectionDocumentPageResponse,
)
async def list_collection_documents(
    collection_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CollectionDocumentPageResponse:
    page = await CollectionService(session).list_documents(
        owner_id=current_user.id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return CollectionDocumentPageResponse(
        documents=[
            CollectionDocumentResponse.model_validate(document, from_attributes=True)
            for document in page.documents
        ],
        total=page.total,
    )


@router.get(
    "/{collection_id}/candidates",
    response_model=CollectionDocumentPageResponse,
)
async def list_collection_candidates(
    collection_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    query: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CollectionDocumentPageResponse:
    try:
        page = await CollectionService(session).list_membership_candidates(
            owner_id=current_user.id,
            collection_id=collection_id,
            query=query,
            limit=limit,
            offset=offset,
        )
    except InvalidCollectionOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return CollectionDocumentPageResponse(
        documents=[
            CollectionDocumentResponse.model_validate(document, from_attributes=True)
            for document in page.documents
        ],
        total=page.total,
    )


@router.post(
    "/{collection_id}/documents/{document_id}",
    response_model=CollectionMembershipResponse,
)
async def add_collection_document(
    collection_id: UUID,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionMembershipResponse:
    try:
        changed = await CollectionService(session).add_document(
            owner_id=current_user.id,
            actor_id=current_user.id,
            collection_id=collection_id,
            document_id=document_id,
        )
    except InvalidCollectionOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if changed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection or document not found",
        )
    return CollectionMembershipResponse(changed=changed)


@router.delete(
    "/{collection_id}/documents/{document_id}",
    response_model=CollectionMembershipResponse,
)
async def remove_collection_document(
    collection_id: UUID,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionMembershipResponse:
    try:
        changed = await CollectionService(session).remove_document(
            owner_id=current_user.id,
            actor_id=current_user.id,
            collection_id=collection_id,
            document_id=document_id,
        )
    except InvalidCollectionOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if changed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return CollectionMembershipResponse(changed=changed)


def document_rule(request: DocumentRuleRequest) -> DocumentRule:
    return DocumentRule.from_mapping(request.model_dump(mode="json"))


def collection_response(summary: CollectionSummary) -> CollectionResponse:
    collection = summary.collection
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        slug=collection.slug,
        description=collection.description,
        color=collection.color,
        kind=CollectionKind(collection.kind),
        view_mode=CollectionView(collection.view_mode),
        rule=DocumentRuleRequest.model_validate(collection.rule),
        document_count=summary.document_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )
