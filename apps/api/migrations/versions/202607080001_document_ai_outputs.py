"""Add document AI analyses and embeddings.

Revision ID: 202607080001
Revises: 202607070002
Create Date: 2026-07-08 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080001"
down_revision: str | None = "202607070002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_ai_analyses",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("text_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("suggested_tags", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("extracted_metadata", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            name="ck_document_ai_analyses_document_ai_analysis_confidence_valid",
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'succeeded')",
            name="ck_document_ai_analyses_document_ai_analysis_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_ai_analyses_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_document_ai_analyses_text_extraction",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_ai_analyses"),
    )
    op.create_index(
        "ix_document_ai_analyses_category",
        "document_ai_analyses",
        ["document_id", "category"],
    )
    op.create_index(
        "ix_document_ai_analyses_current",
        "document_ai_analyses",
        ["document_id", "is_current"],
    )

    op.create_table(
        "document_embeddings",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("text_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("vector_norm", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("source_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "dimensions > 0",
            name="ck_document_embeddings_document_embedding_dimensions_positive",
        ),
        sa.CheckConstraint(
            "vector_norm >= 0",
            name="ck_document_embeddings_vector_norm_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_embeddings_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_document_embeddings_text_extraction",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_embeddings"),
    )
    op.create_index(
        "ix_document_embeddings_current",
        "document_embeddings",
        ["document_id", "is_current"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_embeddings_current", table_name="document_embeddings")
    op.drop_table("document_embeddings")
    op.drop_index("ix_document_ai_analyses_current", table_name="document_ai_analyses")
    op.drop_index("ix_document_ai_analyses_category", table_name="document_ai_analyses")
    op.drop_table("document_ai_analyses")
