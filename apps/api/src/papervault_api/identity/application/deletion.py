from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.deletion import DocumentDeletionService
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.infrastructure.models import Document
from papervault_api.identity.domain.enums import UserRole
from papervault_api.identity.infrastructure.models import User


class InvalidUserDeletionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UserDeletionResult:
    user_id: UUID
    email: str
    deleted_document_ids: tuple[UUID, ...]


class UserDeletionService:
    def __init__(self, *, session: AsyncSession, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage

    async def delete_user(
        self,
        *,
        admin_id: UUID,
        user_id: UUID,
    ) -> UserDeletionResult | None:
        if admin_id == user_id:
            raise InvalidUserDeletionError("Administrators cannot delete their own account")
        user = await self._session.get(User, user_id)
        if user is None:
            return None
        if user.role == UserRole.ADMIN.value and user.is_active:
            active_admins = await self._session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == UserRole.ADMIN.value,
                    User.is_active.is_(True),
                )
            )
            if (active_admins or 0) <= 1:
                raise InvalidUserDeletionError("Cannot delete the last active administrator")

        document_ids = tuple(
            (
                await self._session.execute(select(Document.id).where(Document.owner_id == user_id))
            ).scalars()
        )
        deletion = DocumentDeletionService(session=self._session, storage=self._storage)
        for document_id in document_ids:
            await deletion.delete_document(owner_id=user_id, document_id=document_id)

        user = await self._session.get(User, user_id)
        if user is None:
            return None
        email = user.email
        await self._session.delete(user)
        await self._session.commit()
        return UserDeletionResult(
            user_id=user_id,
            email=email,
            deleted_document_ids=document_ids,
        )
