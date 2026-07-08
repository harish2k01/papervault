from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin
from papervault_api.notifications.domain.enums import NotificationKind, NotificationStatus


class Notification(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        check_values("kind", NotificationKind, "notification_kind_valid"),
        check_values("status", NotificationStatus, "notification_status_valid"),
        Index("ix_notifications_owner_due", "owner_id", "due_date"),
        Index("ix_notifications_owner_status", "owner_id", "status"),
        UniqueConstraint(
            "owner_id",
            "document_id",
            "kind",
            "due_date",
            name="uq_notifications_document_due_kind",
        ),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=NotificationStatus.PENDING.value,
        server_default=NotificationStatus.PENDING.value,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
