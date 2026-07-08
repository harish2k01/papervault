"""Add search history and notifications.

Revision ID: 202607080002
Revises: 202607080001
Create Date: 2026-07-08 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080002"
down_revision: str | None = "202607080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "mode IN ('hybrid', 'keyword', 'semantic')",
            name="ck_saved_searches_saved_search_mode_valid",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_saved_searches_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_saved_searches"),
    )
    op.create_index(
        "ix_saved_searches_owner_created",
        "saved_searches",
        ["owner_id", "created_at"],
    )

    op.create_table(
        "recent_searches",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column(
            "searched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "mode IN ('hybrid', 'keyword', 'semantic')",
            name="ck_recent_searches_recent_search_mode_valid",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_recent_searches_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recent_searches"),
    )
    op.create_index(
        "ix_recent_searches_owner_searched",
        "recent_searches",
        ["owner_id", "searched_at"],
    )

    op.create_table(
        "notifications",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('due_date', 'expiry', 'policy_renewal', 'warranty_expiry')",
            name="ck_notifications_notification_kind_valid",
        ),
        sa.CheckConstraint(
            "status IN ('dismissed', 'pending', 'read')",
            name="ck_notifications_notification_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_notifications_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_notifications_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.UniqueConstraint(
            "owner_id",
            "document_id",
            "kind",
            "due_date",
            name="uq_notifications_document_due_kind",
        ),
    )
    op.create_index("ix_notifications_owner_due", "notifications", ["owner_id", "due_date"])
    op.create_index("ix_notifications_owner_status", "notifications", ["owner_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_notifications_owner_status", table_name="notifications")
    op.drop_index("ix_notifications_owner_due", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_recent_searches_owner_searched", table_name="recent_searches")
    op.drop_table("recent_searches")
    op.drop_index("ix_saved_searches_owner_created", table_name="saved_searches")
    op.drop_table("saved_searches")
