"""Add document text extraction records.

Revision ID: 202607070002
Revises: 202607070001
Create Date: 2026-07-07 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607070002"
down_revision: str | None = "202607070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_text_extractions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("extractor", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_document_text_extractions_document_text_extraction_confidence_valid",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_document_text_extractions_document_text_extraction_page_count_valid",
        ),
        sa.CheckConstraint(
            "source IN ('embedded_text', 'ocr')",
            name="ck_document_text_extractions_document_text_extraction_source_valid",
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'skipped', 'succeeded')",
            name="ck_document_text_extractions_document_text_extraction_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_text_extractions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_text_extractions"),
    )
    op.create_index(
        "ix_document_text_extractions_current",
        "document_text_extractions",
        ["document_id", "is_current"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_text_extractions_current",
        table_name="document_text_extractions",
    )
    op.drop_table("document_text_extractions")
