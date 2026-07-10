"""Add page-aware document text extraction.

Revision ID: 202607110001
Revises: 202607080003
Create Date: 2026-07-11 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607110001"
down_revision: str | None = "202607080003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_text_pages",
        sa.Column("text_extraction_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "page_number > 0",
            name="ck_document_text_pages_document_text_page_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_document_text_pages_text_extraction_id_document_text_extractions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_text_pages"),
        sa.UniqueConstraint(
            "text_extraction_id",
            "page_number",
            name="uq_document_text_pages_extraction_page",
        ),
    )
    op.create_index(
        "ix_document_text_pages_extraction_page",
        "document_text_pages",
        ["text_extraction_id", "page_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_text_pages_extraction_page", table_name="document_text_pages")
    op.drop_table("document_text_pages")
