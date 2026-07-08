from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.tags.api.schemas import CreateTagRequest, TagAssignmentResponse, TagResponse
from papervault_api.tags.application.service import TagService

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagResponse]:
    service = TagService(session)
    tags = await service.list_tags(current_user.id)
    return [
        TagResponse(
            id=tag.id,
            name=tag.name,
            slug=tag.slug,
            description=tag.description,
            color=tag.color,
            source=tag.source,
            created_at=tag.created_at,
        )
        for tag in tags
    ]


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: CreateTagRequest,
) -> TagResponse:
    service = TagService(session)
    tag = await service.create_tag(
        owner_id=current_user.id,
        name=request.name,
        description=request.description,
        color=request.color,
    )
    return TagResponse(
        id=tag.id,
        name=tag.name,
        slug=tag.slug,
        description=tag.description,
        color=tag.color,
        source=tag.source,
        created_at=tag.created_at,
    )


@router.post("/documents/{document_id}/tags/{tag_id}", response_model=TagAssignmentResponse)
async def attach_tag(
    document_id: UUID,
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TagAssignmentResponse:
    service = TagService(session)
    attached = await service.attach_tag(
        owner_id=current_user.id,
        document_id=document_id,
        tag_id=tag_id,
    )
    if not attached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document or tag not found"
        )
    return TagAssignmentResponse(attached=True)


@router.delete("/documents/{document_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_tag(
    document_id: UUID,
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    service = TagService(session)
    detached = await service.detach_tag(
        owner_id=current_user.id,
        document_id=document_id,
        tag_id=tag_id,
    )
    if not detached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document or tag not found"
        )
