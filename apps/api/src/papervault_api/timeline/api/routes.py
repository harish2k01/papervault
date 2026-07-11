from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.timeline.api.schemas import VaultTimelineItemResponse
from papervault_api.timeline.application.read import VaultTimelineReadService

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("", response_model=list[VaultTimelineItemResponse])
async def list_vault_timeline(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: Annotated[str | None, Query(max_length=80)] = None,
    document_id: UUID | None = None,
) -> list[VaultTimelineItemResponse]:
    items = await VaultTimelineReadService(session).list_events(
        owner_id=current_user.id,
        limit=limit,
        offset=offset,
        event_type=event_type,
        document_id=document_id,
    )
    return [VaultTimelineItemResponse.model_validate(item, from_attributes=True) for item in items]
