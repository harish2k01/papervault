from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin
from papervault_api.search.domain.enums import SearchMode


class SavedSearch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        check_values("mode", SearchMode, "saved_search_mode_valid"),
        Index("ix_saved_searches_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default=SearchMode.HYBRID.value)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RecentSearch(UuidPrimaryKeyMixin, Base):
    __tablename__ = "recent_searches"
    __table_args__ = (
        check_values("mode", SearchMode, "recent_search_mode_valid"),
        Index("ix_recent_searches_owner_searched", "owner_id", "searched_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default=SearchMode.HYBRID.value)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
