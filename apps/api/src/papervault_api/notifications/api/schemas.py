from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from papervault_api.notifications.domain.enums import NotificationKind, NotificationStatus


class NotificationResponse(BaseModel):
    id: UUID
    document_id: UUID | None
    kind: NotificationKind
    status: NotificationStatus
    title: str
    message: str
    due_date: date
    payload: dict[str, Any]
    created_at: datetime


class UpdateNotificationStatusRequest(BaseModel):
    status: NotificationStatus
