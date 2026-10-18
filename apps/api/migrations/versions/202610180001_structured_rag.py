"""Separate versioned structured retrieval index.

Revision ID: 202610180001
Revises: 202610170001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610180001"
down_revision: str | None = "202610170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_rag_indexes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "text_extraction_id",
            sa.Uuid(),
            sa.ForeignKey(
                "document_text_extractions.id", ondelete="CASCADE", name="fk_rag_index_extraction"
            ),
            nullable=False,
        ),
        sa.Column("pipeline_id", sa.String(64), nullable=False),
        sa.Column("parser_model", sa.String(200), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_revision", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("covered_pages", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("understanding", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "text_extraction_id", "pipeline_id", name="uq_rag_index_source_pipeline"
        ),
    )
    op.create_index("ix_document_rag_indexes_document_id", "document_rag_indexes", ["document_id"])
    op.create_table(
        "document_rag_passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "index_id",
            sa.Uuid(),
            sa.ForeignKey("document_rag_indexes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.UniqueConstraint("index_id", "ordinal", name="uq_rag_passage_ordinal"),
    )
    op.create_index(
        "ix_rag_passage_index_page", "document_rag_passages", ["index_id", "page_number"]
    )


def downgrade() -> None:
    op.drop_table("document_rag_passages")
    op.drop_table("document_rag_indexes")
