"""Add current source versions and extraction lineage.

Revision ID: 202607110005
Revises: 202607110004
Create Date: 2026-07-11 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607110005"
down_revision: str | None = "202607110004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("original_filename", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        """
        UPDATE document_versions AS version
        SET original_filename = document.original_filename,
            content_type = document.content_type
        FROM documents AS document
        WHERE document.id = version.document_id
        """
    )
    op.execute(
        """
        UPDATE document_versions AS version
        SET is_current = true
        WHERE version.version_number = (
            SELECT MAX(candidate.version_number)
            FROM document_versions AS candidate
            WHERE candidate.document_id = version.document_id
        )
        """
    )
    op.alter_column("document_versions", "original_filename", nullable=False)
    op.alter_column("document_versions", "content_type", nullable=False)
    op.create_index(
        "uq_document_versions_current",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.add_column(
        "document_text_extractions",
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE document_text_extractions AS extraction
        SET document_version_id = version.id
        FROM document_versions AS version
        WHERE version.document_id = extraction.document_id
          AND version.is_current = true
        """
    )
    op.create_foreign_key(
        "fk_text_extractions_document_version",
        "document_text_extractions",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_text_extractions_document_version",
        "document_text_extractions",
        ["document_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_text_extractions_document_version",
        table_name="document_text_extractions",
    )
    op.drop_constraint(
        "fk_text_extractions_document_version",
        "document_text_extractions",
        type_="foreignkey",
    )
    op.drop_column("document_text_extractions", "document_version_id")
    op.drop_index("uq_document_versions_current", table_name="document_versions")
    op.drop_column("document_versions", "is_current")
    op.drop_column("document_versions", "content_type")
    op.drop_column("document_versions", "original_filename")
