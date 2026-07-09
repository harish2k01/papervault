from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.application.oidc import OIDCProvider
from papervault_api.identity.application.service import current_user_from_model
from papervault_api.identity.application.tokens import TokenError, verify_access_token
from papervault_api.identity.domain.enums import AuthProvider, UserRole
from papervault_api.identity.infrastructure.models import User
from papervault_api.identity.infrastructure.oidc import HttpOIDCProvider

bearer_scheme = HTTPBearer(auto_error=False)


def get_oidc_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OIDCProvider:
    return HttpOIDCProvider(settings)


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    dev_user_id: Annotated[UUID | None, Header(alias="X-PaperVault-User-Id")] = None,
    email: Annotated[str | None, Header(alias="X-PaperVault-User-Email")] = None,
) -> CurrentUser:
    if credentials is not None:
        return await _current_user_from_bearer_token(
            session=session,
            settings=settings,
            token=credentials.credentials,
        )

    if settings.dev_auth_enabled:
        return await _current_user_from_dev_headers(
            session=session,
            user_id=dev_user_id,
            email=email,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*roles: UserRole) -> Callable[[CurrentUser], CurrentUser]:
    allowed_roles = set(roles)

    def dependency(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


async def _current_user_from_bearer_token(
    *,
    session: AsyncSession,
    settings: Settings,
    token: str,
) -> CurrentUser:
    try:
        claims = verify_access_token(
            token,
            signing_key=settings.jwt_signing_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await session.get(User, claims.subject)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user is not active",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user_from_model(user)


async def _current_user_from_dev_headers(
    *,
    session: AsyncSession,
    user_id: UUID | None,
    email: str | None,
) -> CurrentUser:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Missing X-PaperVault-User-Id header or bearer token."),
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
