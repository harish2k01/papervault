from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.api.rule_schemas import DocumentRuleRequest
from papervault_api.documents.domain.rules import DocumentRule, InvalidDocumentRuleError
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.search.api.indexing import reindex_document_best_effort
from papervault_api.tags.api.schemas import (
    CreateSmartTagRequest,
    CreateTagRequest,
    SmartTagRefreshResponse,
    TagAssignmentResponse,
    TagResponse,
    UpdateSmartTagRuleRequest,
)
from papervault_api.tags.application.service import (
    InvalidSmartTagRuleError,
    SmartTagRefreshResult,
    TagConflictError,
    TagService,
    TagSummary,
)
from papervault_api.tags.infrastructure.models import Tag

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagResponse]:
    summaries = await TagService(session).list_tag_summaries(current_user.id)
    return [tag_summary_response(summary) for summary in summaries]


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: CreateTagRequest,
) -> TagResponse:
    try:
        tag = await TagService(session).create_tag(
            owner_id=current_user.id,
            name=request.name,
            description=request.description,
            color=request.color,
        )
    except TagConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return tag_response(tag)


@router.post(
    "/tags/smart",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_smart_tag(
    request: CreateSmartTagRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TagResponse:
    rule = document_rule(request.rule.model_dump(mode="json"))
    try:
        tag, refresh = await TagService(session).create_smart_tag(
            owner_id=current_user.id,
            actor_id=current_user.id,
            name=request.name,
            description=request.description,
            color=request.color,
            rule=rule,
        )
    except TagConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidSmartTagRuleError, InvalidDocumentRuleError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await reindex_changed_documents(session, settings, refresh)
    return tag_response(
        tag,
        document_count=refresh.matched,
        smart_rule=rule,
        last_evaluated_at=refresh.evaluated_at,
    )


@router.patch("/tags/{tag_id}/smart-rule", response_model=TagResponse)
async def update_smart_tag_rule(
    tag_id: UUID,
    request: UpdateSmartTagRuleRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TagResponse:
    rule = document_rule(request.rule.model_dump(mode="json"))
    try:
        result = await TagService(session).update_smart_tag_rule(
            owner_id=current_user.id,
            actor_id=current_user.id,
            tag_id=tag_id,
            rule=rule,
        )
    except (InvalidSmartTagRuleError, InvalidDocumentRuleError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart tag not found")
    tag, refresh = result
    await reindex_changed_documents(session, settings, refresh)
    return tag_response(
        tag,
        document_count=refresh.matched,
        smart_rule=rule,
        last_evaluated_at=refresh.evaluated_at,
    )


@router.post("/tags/{tag_id}/refresh", response_model=SmartTagRefreshResponse)
async def refresh_smart_tag(
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SmartTagRefreshResponse:
    result = await TagService(session).refresh_smart_tag(
        owner_id=current_user.id,
        actor_id=current_user.id,
        tag_id=tag_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart tag not found")
    await reindex_changed_documents(session, settings, result)
    return SmartTagRefreshResponse(
        evaluated=result.evaluated,
        matched=result.matched,
        attached=result.attached,
        detached=result.detached,
    )


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    document_ids = await TagService(session).delete_tag(
        owner_id=current_user.id,
        tag_id=tag_id,
    )
    if document_ids is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    for document_id in document_ids:
        await reindex_document_best_effort(
            session=session,
            settings=settings,
            document_id=document_id,
            reason="tag_deleted",
        )


@router.post("/documents/{document_id}/tags/{tag_id}", response_model=TagAssignmentResponse)
async def attach_tag(
    document_id: UUID,
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TagAssignmentResponse:
    attached = await TagService(session).attach_tag(
        owner_id=current_user.id,
        document_id=document_id,
        tag_id=tag_id,
    )
    if not attached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document or tag not found"
        )
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="tag_attached",
    )
    return TagAssignmentResponse(attached=True)


@router.delete("/documents/{document_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_tag(
    document_id: UUID,
    tag_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    detached = await TagService(session).detach_tag(
        owner_id=current_user.id,
        document_id=document_id,
        tag_id=tag_id,
    )
    if not detached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document or tag not found"
        )
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="tag_detached",
    )


async def reindex_changed_documents(
    session: AsyncSession,
    settings: Settings,
    refresh: SmartTagRefreshResult,
) -> None:
    for document_id in refresh.changed_document_ids:
        await reindex_document_best_effort(
            session=session,
            settings=settings,
            document_id=document_id,
            reason="smart_tag_refreshed",
        )


def document_rule(value: dict[str, object]) -> DocumentRule:
    return DocumentRule.from_mapping(value)


def tag_summary_response(summary: TagSummary) -> TagResponse:
    return tag_response(
        summary.tag,
        document_count=summary.document_count,
        smart_rule=summary.smart_rule,
        last_evaluated_at=summary.last_evaluated_at,
    )


def tag_response(
    tag: Tag,
    *,
    document_count: int = 0,
    smart_rule: DocumentRule | None = None,
    last_evaluated_at: datetime | None = None,
) -> TagResponse:
    return TagResponse(
        id=tag.id,
        name=tag.name,
        slug=tag.slug,
        description=tag.description,
        color=tag.color,
        source=tag.source,
        document_count=document_count,
        smart_rule=(
            DocumentRuleRequest.model_validate(smart_rule.as_dict())
            if smart_rule is not None
            else None
        ),
        last_evaluated_at=last_evaluated_at,
        created_at=tag.created_at,
    )
