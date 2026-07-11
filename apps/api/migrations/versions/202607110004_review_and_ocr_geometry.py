"""Add document review state and OCR text geometry.

Revision ID: 202607110004
Revises: 202607110003
Create Date: 2026-07-11 18:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607110004"
down_revision: str | None = "202607110003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="not_required",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("review_reasons", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("documents", sa.Column("reviewed_by_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("review_note", sa.String(length=1000), nullable=True))
    op.create_check_constraint(
        "ck_documents_document_review_status_valid",
        "documents",
        "review_status IN ('approved', 'not_required', 'pending')",
    )
    op.create_foreign_key(
        "fk_documents_reviewed_by_id_users",
        "documents",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_owner_review",
        "documents",
        ["owner_id", "review_status"],
    )

    op.create_table(
        "document_text_blocks",
        sa.Column("text_extraction_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("left_ratio", sa.Numeric(precision=8, scale=7), nullable=False),
        sa.Column("top_ratio", sa.Numeric(precision=8, scale=7), nullable=False),
        sa.Column("width_ratio", sa.Numeric(precision=8, scale=7), nullable=False),
        sa.Column("height_ratio", sa.Numeric(precision=8, scale=7), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "page_number > 0", name="ck_document_text_blocks_text_block_page_positive"
        ),
        sa.CheckConstraint(
            "block_index >= 0", name="ck_document_text_blocks_text_block_index_valid"
        ),
        sa.CheckConstraint(
            "left_ratio >= 0 AND left_ratio <= 1",
            name="ck_document_text_blocks_text_block_left_ratio_valid",
        ),
        sa.CheckConstraint(
            "top_ratio >= 0 AND top_ratio <= 1",
            name="ck_document_text_blocks_text_block_top_ratio_valid",
        ),
        sa.CheckConstraint(
            "width_ratio > 0 AND width_ratio <= 1",
            name="ck_document_text_blocks_text_block_width_ratio_valid",
        ),
        sa.CheckConstraint(
            "height_ratio > 0 AND height_ratio <= 1",
            name="ck_document_text_blocks_text_block_height_ratio_valid",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_document_text_blocks_text_block_confidence_valid",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_text_blocks_extraction",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_text_blocks"),
        sa.UniqueConstraint(
            "text_extraction_id",
            "page_number",
            "block_index",
            name="uq_text_blocks_extraction_page_index",
        ),
    )
    op.create_index(
        "ix_text_blocks_extraction_page",
        "document_text_blocks",
        ["text_extraction_id", "page_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_text_blocks_extraction_page", table_name="document_text_blocks")
    op.drop_table("document_text_blocks")
    op.drop_index("ix_documents_owner_review", table_name="documents")
    op.drop_constraint("fk_documents_reviewed_by_id_users", "documents", type_="foreignkey")
    op.drop_constraint(
        "ck_documents_document_review_status_valid",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "review_note")
    op.drop_column("documents", "reviewed_by_id")
    op.drop_column("documents", "reviewed_at")
    op.drop_column("documents", "review_reasons")
    op.drop_column("documents", "review_status")
