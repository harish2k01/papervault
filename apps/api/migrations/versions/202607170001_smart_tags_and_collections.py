"""Add smart tag rules and document collections.

Revision ID: 202607170001
Revises: 202607120001
Create Date: 2026-07-17 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607170001"
down_revision: str | None = "202607120001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMELINE_CONSTRAINT = "ck_timeline_events_timeline_event_type_valid"
LEGACY_TIMELINE_CONSTRAINT = (
    "ck_timeline_events_ck_timeline_events_timeline_event_type_valid"
)
OLD_TIMELINE_EVENTS = (
    "ai_summary_regenerated",
    "document_archived",
    "document_uploaded",
    "metadata_edited",
    "tags_changed",
    "version_created",
)


def upgrade() -> None:
    op.create_table(
        "document_collections",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "view_mode",
            sa.String(length=16),
            server_default="grid",
            nullable=False,
        ),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('dynamic', 'manual')",
            name="ck_document_collections_document_collection_kind_valid",
        ),
        sa.CheckConstraint(
            "view_mode IN ('grid', 'list')",
            name="ck_document_collections_document_collection_view_valid",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "slug",
            name="uq_document_collections_owner_slug",
        ),
    )
    op.create_index(
        "ix_document_collections_owner_kind",
        "document_collections",
        ["owner_id", "kind"],
    )

    op.create_table(
        "collection_documents",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["document_collections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "document_id"),
    )
    op.create_index(
        "ix_collection_documents_document",
        "collection_documents",
        ["document_id"],
    )

    op.create_table(
        "smart_tag_rules",
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tag_id"),
    )

    op.drop_constraint(
        op.f(LEGACY_TIMELINE_CONSTRAINT),
        "timeline_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f(TIMELINE_CONSTRAINT),
        "timeline_events",
        event_check((*OLD_TIMELINE_EVENTS, "collections_changed")),
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(TIMELINE_CONSTRAINT),
        "timeline_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f(LEGACY_TIMELINE_CONSTRAINT),
        "timeline_events",
        event_check(OLD_TIMELINE_EVENTS),
    )
    op.drop_table("smart_tag_rules")
    op.drop_index("ix_collection_documents_document", table_name="collection_documents")
    op.drop_table("collection_documents")
    op.drop_index(
        "ix_document_collections_owner_kind",
        table_name="document_collections",
    )
    op.drop_table("document_collections")


def event_check(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"event_type IN ({quoted})"
