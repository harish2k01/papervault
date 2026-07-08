from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.db.session import get_session
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.domain.enums import AuthProvider, UserRole
from papervault_api.identity.infrastructure.models import User


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[UUID | None, Header(alias="X-PaperVault-User-Id")] = None,
    email: Annotated[str | None, Header(alias="X-PaperVault-User-Email")] = None,
) -> CurrentUser:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing X-PaperVault-User-Id header. Auth integration arrives in a later phase."
            ),
        )

    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=email or f"{user_id}@local.papervault",
            auth_provider=AuthProvider.LOCAL.value,
            role=UserRole.USER.value,
        )
        session.add(user)
        await session.flush()

    return CurrentUser(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
    )
