from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import UuidPrimaryKeyMixin
from papervault_api.timeline.domain.events import TimelineEventType

if TYPE_CHECKING:
    from papervault_api.documents.infrastructure.models import Document


class TimelineEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        check_values("event_type", TimelineEventType, "timeline_event_type_valid"),
        Index("ix_timeline_events_owner_occurred", "owner_id", "occurred_at"),
        Index("ix_timeline_events_document_occurred", "document_id", "occurred_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document | None] = relationship(back_populates="timeline_events")
