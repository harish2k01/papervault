"""Versioned candidate index; existing extraction and analysis remain authoritative."""

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from papervault_api.db.base import Base
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin


class DocumentRagIndex(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_rag_indexes"
    __table_args__ = (
        UniqueConstraint("text_extraction_id", "pipeline_id", name="uq_rag_index_source_pipeline"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text_extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_text_extractions.id", ondelete="CASCADE", name="fk_rag_index_extraction"
        ),
        nullable=False,
    )
    pipeline_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    covered_pages: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Separate from the production summary. Every finding carries source passage IDs/quotes.
    understanding: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class DocumentRagPassage(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_rag_passages"
    __table_args__ = (
        UniqueConstraint("index_id", "ordinal", name="uq_rag_passage_ordinal"),
        Index("ix_rag_passage_index_page", "index_id", "page_number"),
    )

    index_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_rag_indexes.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
