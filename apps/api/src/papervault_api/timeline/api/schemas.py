from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VaultTimelineItemResponse(BaseModel):
    id: UUID
    document_id: UUID | None
    document_title: str | None
    event_type: str
    payload: dict[str, object]
    occurred_at: datetime
