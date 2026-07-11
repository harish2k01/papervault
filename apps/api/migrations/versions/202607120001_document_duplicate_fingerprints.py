"""Add document duplicate fingerprints and locality-sensitive buckets.

Revision ID: 202607120001
Revises: 202607110005
Create Date: 2026-07-12 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607120001"
down_revision: str | None = "202607110005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_duplicate_fingerprints",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("text_extraction_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("algorithm_version", sa.Integer(), nullable=False),
        sa.Column("normalized_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("minhash_signature", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("shingle_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
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
            "algorithm_version > 0",
            name="algorithm_version_positive",
        ),
        sa.CheckConstraint("token_count > 0", name="token_count_positive"),
        sa.CheckConstraint(
            "shingle_count > 0",
            name="shingle_count_positive",
        ),
        sa.CheckConstraint(
            "character_count > 0",
            name="character_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_duplicate_fingerprints_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_extraction_id"],
            ["document_text_extractions.id"],
            name="fk_duplicate_fingerprints_extraction",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_duplicate_fingerprints_document"),
    )
    op.create_index(
        "ix_duplicate_fingerprints_normalized_hash",
        "document_duplicate_fingerprints",
        ["normalized_text_sha256"],
    )
    op.create_index(
        "ix_duplicate_fingerprints_extraction",
        "document_duplicate_fingerprints",
        ["text_extraction_id"],
    )

    op.create_table(
        "document_duplicate_buckets",
        sa.Column("fingerprint_id", sa.Uuid(), nullable=False),
        sa.Column("band_index", sa.Integer(), nullable=False),
        sa.Column("bucket_hash", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fingerprint_id"],
            ["document_duplicate_fingerprints.id"],
            name="fk_duplicate_buckets_fingerprint",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fingerprint_id",
            "band_index",
            name="uq_duplicate_buckets_fingerprint_band",
        ),
    )
    op.create_index(
        "ix_duplicate_buckets_lookup",
        "document_duplicate_buckets",
        ["band_index", "bucket_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_duplicate_buckets_lookup", table_name="document_duplicate_buckets")
    op.drop_table("document_duplicate_buckets")
    op.drop_index(
        "ix_duplicate_fingerprints_extraction",
        table_name="document_duplicate_fingerprints",
    )
    op.drop_index(
        "ix_duplicate_fingerprints_normalized_hash",
        table_name="document_duplicate_fingerprints",
    )
    op.drop_table("document_duplicate_fingerprints")
