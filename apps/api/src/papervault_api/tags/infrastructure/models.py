from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin
from papervault_api.tags.domain.enums import TagSource

if TYPE_CHECKING:
    from papervault_api.documents.infrastructure.models import Document


class Tag(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_tags_owner_slug"),
        check_values("source", TagSource, "tag_source_valid"),
        Index("ix_tags_owner_source", "owner_id", "source"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    color: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TagSource.MANUAL.value,
        server_default=TagSource.MANUAL.value,
    )

    document_links: Mapped[list[DocumentTag]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    smart_rule: Mapped[SmartTagRule | None] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="document_tag_confidence_valid",
        ),
        check_values("source", TagSource, "document_tag_source_valid"),
        Index("ix_document_tags_tag_id", "tag_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TagSource.MANUAL.value,
        server_default=TagSource.MANUAL.value,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    assigned_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="document_links")


class SmartTagRule(Base):
    __tablename__ = "smart_tag_rules"

    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tag: Mapped[Tag] = relationship(back_populates="smart_rule")
