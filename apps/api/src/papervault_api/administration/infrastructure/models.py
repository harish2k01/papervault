from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from papervault_api.db.base import Base


class InstanceSettings(Base):
    __tablename__ = "instance_settings"
    __table_args__ = (CheckConstraint("id = 1", name="instance_settings_singleton"),)

    id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        default=1,
        server_default="1",
    )
    local_registration_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", name="fk_instance_settings_updated_by", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
