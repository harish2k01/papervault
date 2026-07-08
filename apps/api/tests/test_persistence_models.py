from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.db import models as _models  # noqa: F401
from papervault_api.db.base import Base
from papervault_api.documents.domain.models import NewDocumentRecord
from papervault_api.documents.infrastructure.repositories import SqlAlchemyDocumentRepository
from papervault_api.identity.infrastructure.models import User


def test_core_schema_metadata_contains_expected_tables() -> None:
    table_names = set(Base.metadata.tables)

    assert {
        "users",
        "documents",
        "document_ai_analyses",
        "document_embeddings",
        "document_versions",
        "document_metadata",
        "document_text_extractions",
        "tags",
        "document_tags",
        "timeline_events",
    }.issubset(table_names)


async def test_schema_can_be_created(session: AsyncSession) -> None:
    connection = await session.connection()
    table_names = await connection.run_sync(
        lambda sync_connection: inspect(sync_connection).get_table_names()
    )

    assert "documents" in table_names
    assert "timeline_events" in table_names


async def test_document_repository_adds_and_reads_document(session: AsyncSession) -> None:
    user = User(email="person@example.com", display_name="Person")
    session.add(user)
    await session.flush()

    repository = SqlAlchemyDocumentRepository(session)
    created = await repository.add(
        NewDocumentRecord(
            owner_id=user.id,
            title="January Salary Slip",
            original_filename="salary-jan-2025.pdf",
            content_type="application/pdf",
            file_size_bytes=12345,
            sha256_hash="a" * 64,
            storage_bucket="documents",
            storage_key=f"{user.id}/salary-jan-2025.pdf",
            document_type="salary_slip",
        ),
    )

    found = await repository.get_for_owner(created.id, user.id)

    assert found is not None
    assert found.id == created.id
    assert found.document_type == "salary_slip"
    assert found.original_filename == "salary-jan-2025.pdf"
