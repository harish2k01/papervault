from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from papervault_api.db.base import Base
from papervault_api.db.constraints import check_values
from papervault_api.db.mixins import TimestampMixin, UuidPrimaryKeyMixin
from papervault_api.documents.domain.enums import (
    AIAnalysisStatus,
    DocumentReviewStatus,
    DocumentSourceKind,
    DocumentStatus,
    MetadataSource,
    TextExtractionSource,
    TextExtractionStatus,
)

if TYPE_CHECKING:
    from papervault_api.tags.infrastructure.models import DocumentTag
    from papervault_api.timeline.infrastructure.models import TimelineEvent


class Document(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size_bytes >= 0", name="document_file_size_non_negative"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="document_page_count_valid"),
        check_values("source_kind", DocumentSourceKind, "document_source_kind_valid"),
        check_values("status", DocumentStatus, "document_status_valid"),
        check_values("review_status", DocumentReviewStatus, "document_review_status_valid"),
        UniqueConstraint("storage_bucket", "storage_key", name="uq_documents_storage_object"),
        Index("ix_documents_owner_status", "owner_id", "status"),
        Index("ix_documents_owner_type", "owner_id", "document_type"),
        Index("ix_documents_owner_date", "owner_id", "document_date"),
        Index("ix_documents_owner_review", "owner_id", "review_status"),
        Index("ix_documents_sha256_hash", "sha256_hash"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_version_id: Mapped[str | None] = mapped_column(String(255))
    source_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentSourceKind.UPLOAD.value,
        server_default=DocumentSourceKind.UPLOAD.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
        server_default=DocumentStatus.UPLOADED.value,
    )
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, default="generic_pdf")
    document_date: Mapped[date | None] = mapped_column(Date)
    issuer: Mapped[str | None] = mapped_column(String(255))
    organization: Mapped[str | None] = mapped_column(String(255))
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(Text)
    processing_error: Mapped[str | None] = mapped_column(Text)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentReviewStatus.NOT_REQUIRED.value,
        server_default=DocumentReviewStatus.NOT_REQUIRED.value,
    )
    review_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_note: Mapped[str | None] = mapped_column(String(1000))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_records: Mapped[list[DocumentMetadataRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ai_analyses: Mapped[list[DocumentAIAnalysis]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    embeddings: Mapped[list[DocumentEmbedding]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    text_chunks: Mapped[list[DocumentTextChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    text_extractions: Mapped[list[DocumentTextExtraction]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    duplicate_fingerprint: Mapped[DocumentDuplicateFingerprint | None] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    tag_links: Mapped[list[DocumentTag]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    timeline_events: Mapped[list[TimelineEvent]] = relationship(back_populates="document")


class DocumentVersion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="document_version_number_positive"),
        CheckConstraint("file_size_bytes >= 0", name="document_version_file_size_non_negative"),
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        Index(
            "uq_document_versions_current",
            "document_id",
            unique=True,
            postgresql_where=sql_text("is_current"),
            sqlite_where=sql_text("is_current = 1"),
        ),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_version_id: Mapped[str | None] = mapped_column(String(255))
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    change_reason: Mapped[str | None] = mapped_column(String(255))
    is_current: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentMetadataRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_metadata"
    __table_args__ = (
        CheckConstraint("schema_version > 0", name="document_metadata_schema_version_positive"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="document_metadata_confidence_valid",
        ),
        check_values("source", MetadataSource, "document_metadata_source_valid"),
        Index("ix_document_metadata_document_current", "document_id", "is_current"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_name: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MetadataSource.AI.value,
        server_default=MetadataSource.AI.value,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extractor: Mapped[str | None] = mapped_column(String(120))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")

    document: Mapped[Document] = relationship(back_populates="metadata_records")


class DocumentAIAnalysis(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_ai_analyses"
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="document_ai_analysis_confidence_valid",
        ),
        check_values("status", AIAnalysisStatus, "document_ai_analysis_status_valid"),
        Index("ix_document_ai_analyses_current", "document_id", "is_current"),
        Index("ix_document_ai_analyses_category", "document_id", "category"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_extraction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_document_ai_analyses_text_extraction",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    suggested_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str | None] = mapped_column(String(80))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extracted_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")

    document: Mapped[Document] = relationship(back_populates="ai_analyses")


class DocumentEmbedding(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_embeddings"
    __table_args__ = (
        CheckConstraint("dimensions > 0", name="document_embedding_dimensions_positive"),
        CheckConstraint("vector_norm >= 0", name="embedding_vector_norm_non_negative"),
        Index("ix_document_embeddings_current", "document_id", "is_current"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_extraction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_document_embeddings_text_extraction",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    vector_norm: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    source_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")

    document: Mapped[Document] = relationship(back_populates="embeddings")


class DocumentTextExtraction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_text_extractions"
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="text_extraction_confidence_valid",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="text_extraction_page_count_valid",
        ),
        check_values("source", TextExtractionSource, "text_extraction_source_valid"),
        check_values("status", TextExtractionStatus, "text_extraction_status_valid"),
        Index("ix_document_text_extractions_current", "document_id", "is_current"),
        Index("ix_text_extractions_document_version", "document_version_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "document_versions.id",
            name="fk_text_extractions_document_version",
            ondelete="SET NULL",
        ),
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(16))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extractor: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")

    document: Mapped[Document] = relationship(back_populates="text_extractions")
    pages: Mapped[list[DocumentTextPage]] = relationship(
        back_populates="text_extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentTextPage.page_number",
    )
    blocks: Mapped[list[DocumentTextBlock]] = relationship(
        back_populates="text_extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentTextBlock.page_number, DocumentTextBlock.block_index",
    )
    chunks: Mapped[list[DocumentTextChunk]] = relationship(
        back_populates="text_extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentTextChunk.chunk_index",
    )


class DocumentDuplicateFingerprint(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_duplicate_fingerprints"
    __table_args__ = (
        CheckConstraint(
            "algorithm_version > 0",
            name="algorithm_version_positive",
        ),
        CheckConstraint(
            "token_count > 0",
            name="token_count_positive",
        ),
        CheckConstraint(
            "shingle_count > 0",
            name="shingle_count_positive",
        ),
        CheckConstraint(
            "character_count > 0",
            name="character_count_positive",
        ),
        UniqueConstraint("document_id", name="uq_duplicate_fingerprints_document"),
        Index("ix_duplicate_fingerprints_normalized_hash", "normalized_text_sha256"),
        Index("ix_duplicate_fingerprints_extraction", "text_extraction_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_duplicate_fingerprints_document",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    text_extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_duplicate_fingerprints_extraction",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm_version: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    minhash_signature: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shingle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped[Document] = relationship(back_populates="duplicate_fingerprint")
    buckets: Mapped[list[DocumentDuplicateBucket]] = relationship(
        back_populates="fingerprint",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentDuplicateBucket(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_duplicate_buckets"
    __table_args__ = (
        UniqueConstraint(
            "fingerprint_id",
            "band_index",
            name="uq_duplicate_buckets_fingerprint_band",
        ),
        Index("ix_duplicate_buckets_lookup", "band_index", "bucket_hash"),
    )

    fingerprint_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_duplicate_fingerprints.id",
            name="fk_duplicate_buckets_fingerprint",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    band_index: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket_hash: Mapped[str] = mapped_column(String(32), nullable=False)

    fingerprint: Mapped[DocumentDuplicateFingerprint] = relationship(back_populates="buckets")


class DocumentTextPage(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_text_pages"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="document_text_page_number_positive"),
        UniqueConstraint(
            "text_extraction_id",
            "page_number",
            name="uq_document_text_pages_extraction_page",
        ),
        Index("ix_document_text_pages_extraction_page", "text_extraction_id", "page_number"),
    )

    text_extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_text_pages_extraction",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)

    text_extraction: Mapped[DocumentTextExtraction] = relationship(back_populates="pages")


class DocumentTextBlock(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_text_blocks"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="text_block_page_positive"),
        CheckConstraint("block_index >= 0", name="text_block_index_valid"),
        CheckConstraint(
            "left_ratio >= 0 AND left_ratio <= 1",
            name="text_block_left_ratio_valid",
        ),
        CheckConstraint("top_ratio >= 0 AND top_ratio <= 1", name="text_block_top_ratio_valid"),
        CheckConstraint(
            "width_ratio > 0 AND width_ratio <= 1",
            name="text_block_width_ratio_valid",
        ),
        CheckConstraint(
            "height_ratio > 0 AND height_ratio <= 1",
            name="text_block_height_ratio_valid",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="text_block_confidence_valid",
        ),
        UniqueConstraint(
            "text_extraction_id",
            "page_number",
            "block_index",
            name="uq_text_blocks_extraction_page_index",
        ),
        Index("ix_text_blocks_extraction_page", "text_extraction_id", "page_number"),
    )

    text_extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_text_blocks_extraction",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    left_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 7), nullable=False)
    top_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 7), nullable=False)
    width_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 7), nullable=False)
    height_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 7), nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    text_extraction: Mapped[DocumentTextExtraction] = relationship(back_populates="blocks")


class DocumentTextChunk(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_text_chunks"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="chunk_page_positive"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_valid"),
        CheckConstraint("token_count > 0", name="chunk_tokens_positive"),
        CheckConstraint("dimensions > 0", name="chunk_dimensions_positive"),
        CheckConstraint("vector_norm >= 0", name="chunk_norm_non_negative"),
        UniqueConstraint(
            "text_extraction_id",
            "page_number",
            "chunk_index",
            name="uq_text_chunks_extraction_page_index",
        ),
        Index("ix_text_chunks_document_page", "document_id", "page_number"),
        Index("ix_text_chunks_extraction", "text_extraction_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_text_extractions.id",
            name="fk_text_chunks_extraction",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    vector_norm: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    source_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    document: Mapped[Document] = relationship(back_populates="text_chunks")
    text_extraction: Mapped[DocumentTextExtraction] = relationship(back_populates="chunks")
