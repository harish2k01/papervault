"""Persist analysis source evidence and coverage.

Revision ID: 202610170001
Revises: 202607170001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610170001"
down_revision: str | None = "202607170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("field_evidence", "summary_evidence", "quality_warnings", "covered_pages"):
        op.add_column(
            "document_ai_analyses", sa.Column(name, sa.JSON(), nullable=False, server_default="[]")
        )
    op.create_table(
        "document_tag_suppressions",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id", sa.Uuid(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
        ),
    )


def downgrade() -> None:
    op.drop_table("document_tag_suppressions")
    for name in ("covered_pages", "quality_warnings", "summary_evidence", "field_evidence"):
        op.drop_column("document_ai_analyses", name)
