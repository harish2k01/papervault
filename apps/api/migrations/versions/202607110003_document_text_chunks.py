"""Add embedded page text chunks for grounded retrieval.

Revision ID: 202607110003
Revises: 202607110002
Create Date: 2026-07-11 07:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607110003"
down_revision: str | None = "202607110002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_text_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("text_extraction_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("vector_norm", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("source_text_sha256", sa.String(length=64), nullable=False),
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
        sa.CheckConstraint("page_number > 0", name="ck_document_text_chunks_chunk_page_positive"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_text_chunks_chunk_index_valid"),
        sa.CheckConstraint("token_count > 0", name="ck_document_text_chunks_chunk_tokens_positive"),
        sa.CheckConstraint(
            "dimensions > 0", name="ck_document_text_chunks_chunk_dimensions_positive"
        ),
        sa.CheckConstraint(
            "vector_norm >= 0", name="ck_document_text_chunks_chunk_norm_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_text_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_text_chunks_extraction",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_text_chunks"),
        sa.UniqueConstraint(
            "text_extraction_id",
            "page_number",
            "chunk_index",
            name="uq_text_chunks_extraction_page_index",
        ),
    )
    op.create_index(
        "ix_text_chunks_document_page",
        "document_text_chunks",
        ["document_id", "page_number"],
    )
    op.create_index(
        "ix_text_chunks_extraction",
        "document_text_chunks",
        ["text_extraction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_text_chunks_extraction", table_name="document_text_chunks")
    op.drop_index("ix_text_chunks_document_page", table_name="document_text_chunks")
    op.drop_table("document_text_chunks")
