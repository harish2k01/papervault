from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import get_current_user, require_roles
from papervault_api.identity.api.schemas import (
    AuthConfigResponse,
    AuthUserResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateUserRequest,
)
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.application.service import (
    AuthenticationFailedError,
    IdentityService,
    LocalAuthDisabledError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from papervault_api.identity.domain.enums import AuthProvider, UserRole
from papervault_api.identity.infrastructure.models import User

router = APIRouter(tags=["identity"])


@router.get("/auth/config", response_model=AuthConfigResponse)
async def get_auth_config(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthConfigResponse:
    return AuthConfigResponse(
        local_auth_enabled=settings.local_auth_enabled,
        local_registration_enabled=settings.local_registration_enabled,
        dev_headers_enabled=settings.dev_auth_enabled,
        oidc_configured=bool(settings.oidc_issuer_url and settings.oidc_client_id),
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    service = IdentityService(session, settings)
    try:
        user = await service.register_local_user(
            email=request.email,
            password=request.password,
            display_name=request.display_name,
        )
    except (LocalAuthDisabledError, RegistrationDisabledError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WeakPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return token_response(user=user, service=service, settings=settings)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    service = IdentityService(session, settings)
    try:
        user = await service.authenticate_local_user(
            email=request.email,
            password=request.password,
        )
    except LocalAuthDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AuthenticationFailedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return token_response(user=user, service=service, settings=settings)


@router.get("/auth/me", response_model=AuthUserResponse)
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUserResponse:
    user = await IdentityService(session, settings).get_user_by_id(current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_response(user)


@router.get("/users", response_model=list[AuthUserResponse])
async def list_users(
    _admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AuthUserResponse]:
    service = IdentityService(session, settings)
    return [user_response(user) for user in await service.list_users()]


@router.patch("/users/{user_id}", response_model=AuthUserResponse)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUserResponse:
    if user_id == admin.id and request.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot disable their own account",
        )

    service = IdentityService(session, settings)
    existing_user = await service.get_user_by_id(user_id)
    if existing_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    removes_admin_access = existing_user.role == UserRole.ADMIN.value and (
        request.is_active is False or request.role not in (None, UserRole.ADMIN)
    )
    if removes_admin_access and await service.count_active_admins() <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the last active administrator",
        )

    user = await service.update_user(
        user_id=user_id,
        display_name=request.display_name,
        role=request.role,
        is_active=request.is_active,
    )
    assert user is not None
    return user_response(user)


def token_response(*, user: User, service: IdentityService, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=service.create_access_token_for_user(user),
        expires_in_seconds=settings.jwt_access_token_minutes * 60,
        user=user_response(user),
    )


def user_response(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=UserRole(user.role),
        auth_provider=AuthProvider(user.auth_provider),
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
