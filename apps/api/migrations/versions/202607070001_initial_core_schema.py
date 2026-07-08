"""Initial core schema.

Revision ID: 202607070001
Revises:
Create Date: 2026-07-07 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607070001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("auth_provider", sa.String(length=40), server_default="local", nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=40), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("disabled_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "auth_provider IN ('local', 'oidc')",
            name="ck_users_user_auth_provider_valid",
        ),
        sa.CheckConstraint("role IN ('admin', 'user')", name="ck_users_user_role_valid"),
        sa.ForeignKeyConstraint(
            ["disabled_by_id"],
            ["users.id"],
            name="fk_users_disabled_by_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("auth_provider", "external_subject", name="uq_users_external_identity"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "documents",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_bucket", sa.String(length=63), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_version_id", sa.String(length=255), nullable=True),
        sa.Column("source_kind", sa.String(length=32), server_default="upload", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="uploaded", nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "file_size_bytes >= 0", name="ck_documents_document_file_size_non_negative"
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_documents_document_page_count_valid",
        ),
        sa.CheckConstraint(
            "source_kind IN ('api', 'import', 'upload')",
            name="ck_documents_document_source_kind_valid",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'archived', 'failed', 'pending_processing', 'processing', 'ready', 'uploaded'"
            ")",
            name="ck_documents_document_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_documents_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("storage_bucket", "storage_key", name="uq_documents_storage_object"),
    )
    op.create_index("ix_documents_owner_date", "documents", ["owner_id", "document_date"])
    op.create_index("ix_documents_owner_status", "documents", ["owner_id", "status"])
    op.create_index("ix_documents_owner_type", "documents", ["owner_id", "document_type"])
    op.create_index("ix_documents_sha256_hash", "documents", ["sha256_hash"])

    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_bucket", sa.String(length=63), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_version_id", sa.String(length=255), nullable=True),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("change_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_document_versions_document_version_file_size_non_negative",
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_document_versions_document_version_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_document_versions_created_by_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
    )

    op.create_table(
        "document_metadata",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="ai", nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("extractor", sa.String(length=120), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_document_metadata_document_metadata_confidence_valid",
        ),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_document_metadata_document_metadata_schema_version_positive",
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'import', 'manual', 'ocr')",
            name="ck_document_metadata_document_metadata_source_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_metadata_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_metadata"),
    )
    op.create_index(
        "ix_document_metadata_document_current",
        "document_metadata",
        ["document_id", "is_current"],
    )

    op.create_table(
        "tags",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'manual', 'smart')",
            name="ck_tags_tag_source_valid",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_tags_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_tags_owner_slug"),
    )
    op.create_index("ix_tags_owner_source", "tags", ["owner_id", "source"])

    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("assigned_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_document_tags_document_tag_confidence_valid",
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'manual', 'smart')",
            name="ck_document_tags_document_tag_source_valid",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            name="fk_document_tags_assigned_by_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_tags_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name="fk_document_tags_tag_id_tags",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "tag_id", name="pk_document_tags"),
    )
    op.create_index("ix_document_tags_tag_id", "document_tags", ["tag_id"])

    op.create_table(
        "timeline_events",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'ai_summary_regenerated', 'document_archived', 'document_uploaded', "
            "'metadata_edited', 'tags_changed', 'version_created'"
            ")",
            name="ck_timeline_events_timeline_event_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_timeline_events_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_timeline_events_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_timeline_events_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_timeline_events"),
    )
    op.create_index(
        "ix_timeline_events_document_occurred",
        "timeline_events",
        ["document_id", "occurred_at"],
    )
    op.create_index(
        "ix_timeline_events_owner_occurred",
        "timeline_events",
        ["owner_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_events_owner_occurred", table_name="timeline_events")
    op.drop_index("ix_timeline_events_document_occurred", table_name="timeline_events")
    op.drop_table("timeline_events")
    op.drop_index("ix_document_tags_tag_id", table_name="document_tags")
    op.drop_table("document_tags")
    op.drop_index("ix_tags_owner_source", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_document_metadata_document_current", table_name="document_metadata")
    op.drop_table("document_metadata")
    op.drop_table("document_versions")
    op.drop_index("ix_documents_sha256_hash", table_name="documents")
    op.drop_index("ix_documents_owner_type", table_name="documents")
    op.drop_index("ix_documents_owner_status", table_name="documents")
    op.drop_index("ix_documents_owner_date", table_name="documents")
    op.drop_table("documents")
    op.drop_table("users")
