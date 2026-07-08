from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.notifications.api.schemas import (
    NotificationResponse,
    UpdateNotificationStatusRequest,
)
from papervault_api.notifications.application.service import NotificationService
from papervault_api.notifications.domain.enums import NotificationKind, NotificationStatus
from papervault_api.notifications.infrastructure.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    notification_status: NotificationStatus | None = None,
) -> list[NotificationResponse]:
    service = NotificationService(session)
    notifications = await service.list_notifications(
        owner_id=current_user.id,
        status=notification_status,
    )
    return [notification_response(notification) for notification in notifications]


@router.post("/sync/{document_id}", response_model=list[NotificationResponse])
async def sync_document_notifications(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[NotificationResponse]:
    service = NotificationService(session)
    notifications = await service.generate_for_document(document_id)
    owned_notifications = [
        notification for notification in notifications if notification.owner_id == current_user.id
    ]
    return [notification_response(notification) for notification in owned_notifications]


@router.patch("/{notification_id}", response_model=NotificationResponse)
async def update_notification_status(
    notification_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: UpdateNotificationStatusRequest,
) -> NotificationResponse:
    service = NotificationService(session)
    notification = await service.update_status(
        owner_id=current_user.id,
        notification_id=notification_id,
        status=request.status,
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification_response(notification)


def notification_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        document_id=notification.document_id,
        kind=NotificationKind(notification.kind),
        status=NotificationStatus(notification.status),
        title=notification.title,
        message=notification.message,
        due_date=notification.due_date,
        payload=notification.payload,
        created_at=notification.created_at,
    )
