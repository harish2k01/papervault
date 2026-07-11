from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.storage import StoredObject
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.infrastructure.models import Document, DocumentVersion
from papervault_api.identity.application.deletion import (
    InvalidUserDeletionError,
    UserDeletionService,
)
from papervault_api.identity.domain.enums import UserRole
from papervault_api.identity.infrastructure.models import User


class DeletionStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    async def put_file(
        self,
        *,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        raise NotImplementedError

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        raise NotImplementedError

    async def delete_file(self, *, bucket: str, key: str) -> None:
        self.deleted.append((bucket, key))


async def test_admin_can_delete_user_and_owned_source_objects(session: AsyncSession) -> None:
    admin = User(email="admin@example.com", role=UserRole.ADMIN.value)
    target = User(email="target@example.com")
    session.add_all((admin, target))
    await session.flush()
    document = Document(
        owner_id=target.id,
        title="Target document",
        original_filename="target.pdf",
        content_type="application/pdf",
        file_size_bytes=10,
        sha256_hash="a" * 64,
        storage_bucket="documents",
        storage_key="target/source.pdf",
        status=DocumentStatus.READY.value,
        document_type="generic_pdf",
    )
    session.add(document)
    await session.flush()
    session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=1,
            original_filename="target.pdf",
            content_type="application/pdf",
            storage_bucket="documents",
            storage_key="target/source.pdf",
            sha256_hash="a" * 64,
            file_size_bytes=10,
            is_current=True,
        )
    )
    await session.commit()
    storage = DeletionStorage()

    result = await UserDeletionService(session=session, storage=storage).delete_user(
        admin_id=admin.id,
        user_id=target.id,
    )

    assert result is not None
    assert result.deleted_document_ids == (document.id,)
    assert await session.get(User, target.id) is None
    assert await session.get(Document, document.id) is None
    assert storage.deleted == [("documents", "target/source.pdf")]


async def test_admin_cannot_delete_self(session: AsyncSession) -> None:
    admin = User(email="admin-self@example.com", role=UserRole.ADMIN.value)
    session.add(admin)
    await session.commit()

    with pytest.raises(InvalidUserDeletionError, match="own account"):
        await UserDeletionService(session=session, storage=DeletionStorage()).delete_user(
            admin_id=admin.id,
            user_id=admin.id,
        )
