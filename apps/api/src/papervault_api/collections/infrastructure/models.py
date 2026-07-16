from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from papervault_api.collections.domain.enums import CollectionKind, CollectionView
from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from papervault_api.documents.infrastructure.models import Document


class VaultCollection(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_collections"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_document_collections_owner_slug"),
        check_values("kind", CollectionKind, "document_collection_kind_valid"),
        check_values("view_mode", CollectionView, "document_collection_view_valid"),
        Index("ix_document_collections_owner_kind", "owner_id", "kind"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    color: Mapped[str | None] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    view_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=CollectionView.GRID.value,
        server_default=CollectionView.GRID.value,
    )
    rule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    document_links: Mapped[list[CollectionDocument]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CollectionDocument(Base):
    __tablename__ = "collection_documents"
    __table_args__ = (Index("ix_collection_documents_document", "document_id"),)

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    collection: Mapped[VaultCollection] = relationship(back_populates="document_links")
    document: Mapped[Document] = relationship()
