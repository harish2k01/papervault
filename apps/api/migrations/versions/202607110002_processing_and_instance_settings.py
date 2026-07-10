"""Add processing diagnostics and instance settings.

Revision ID: 202607110002
Revises: 202607110001
Create Date: 2026-07-11 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607110002"
down_revision: str | None = "202607110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("local_registration_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_instance_settings_singleton"),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_instance_settings_updated_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_instance_settings"),
    )


def downgrade() -> None:
    op.drop_table("instance_settings")
    op.drop_column("documents", "processing_completed_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "processing_error")
