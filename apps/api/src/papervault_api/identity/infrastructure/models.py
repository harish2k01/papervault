from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin
from papervault_api.identity.domain.enums import AuthProvider, UserRole


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "external_subject", name="uq_users_external_identity"),
        check_values("auth_provider", AuthProvider, "user_auth_provider_valid"),
        check_values("role", UserRole, "user_role_valid"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    auth_provider: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=AuthProvider.LOCAL.value,
        server_default=AuthProvider.LOCAL.value,
    )
    external_subject: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    disabled_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
