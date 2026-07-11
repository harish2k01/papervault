from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.administration.application.service import InstanceSettingsService
from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.api.dependencies import get_object_storage
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.identity.api.dependencies import (
    get_current_user,
    get_oidc_provider,
    require_roles,
)
from papervault_api.identity.api.schemas import (
    AuthConfigResponse,
    AuthUserResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateUserRequest,
)
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.application.deletion import (
    InvalidUserDeletionError,
    UserDeletionService,
)
from papervault_api.identity.application.oidc import (
    OIDCConfigurationError,
    OIDCError,
    OIDCProvider,
)
from papervault_api.identity.application.oidc_state import (
    OIDCStateError,
    create_oidc_state,
    verify_oidc_state,
)
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
from papervault_api.search.api.indexing import reindex_document_best_effort

router = APIRouter(tags=["identity"])


@router.get("/auth/config", response_model=AuthConfigResponse)
async def get_auth_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthConfigResponse:
    instance_settings = await InstanceSettingsService(session, settings).get_effective()
    return AuthConfigResponse(
        local_auth_enabled=settings.local_auth_enabled,
        local_registration_enabled=instance_settings.local_registration_enabled,
        dev_headers_enabled=settings.dev_auth_enabled,
        oidc_configured=settings.oidc_login_enabled,
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    service = IdentityService(session, settings)
    instance_settings = await InstanceSettingsService(session, settings).get_effective()
    try:
        user = await service.register_local_user(
            email=request.email,
            password=request.password,
            display_name=request.display_name,
            registration_enabled=instance_settings.local_registration_enabled,
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


@router.get("/auth/oidc/start")
async def start_oidc_login(
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[OIDCProvider, Depends(get_oidc_provider)],
    redirect_to: Annotated[str | None, Query(max_length=2048)] = "/",
) -> RedirectResponse:
    redirect_uri = require_oidc_redirect_uri(settings)
    try:
        state = create_oidc_state(
            signing_key=settings.jwt_signing_key,
            redirect_to=redirect_to,
            ttl_seconds=settings.oidc_state_ttl_seconds,
        )
        authorization_url = await provider.authorization_url(
            state=state.token,
            nonce=state.nonce,
            redirect_uri=redirect_uri,
        )
    except OIDCStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OIDCConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/oidc/callback")
async def oidc_callback(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[OIDCProvider, Depends(get_oidc_provider)],
    code: Annotated[str | None, Query(max_length=4096)] = None,
    state: Annotated[str | None, Query(max_length=4096)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
    error_description: Annotated[str | None, Query(max_length=1024)] = None,
) -> RedirectResponse:
    if error is not None:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error=error,
            error_description=error_description or "OIDC provider rejected the login request",
        )
    if code is None or state is None:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error="invalid_request",
            error_description="OIDC callback is missing code or state",
        )

    redirect_uri = require_oidc_redirect_uri(settings)
    try:
        verified_state = verify_oidc_state(
            token=state,
            signing_key=settings.jwt_signing_key,
        )
        token_set = await provider.exchange_code(code=code, redirect_uri=redirect_uri)
        claims = await provider.verify_id_token(
            id_token=token_set.id_token,
            nonce=verified_state.nonce,
        )
        service = IdentityService(session, settings)
        user = await service.authenticate_oidc_user(claims=claims)
    except OIDCStateError as exc:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error="invalid_state",
            error_description=str(exc),
        )
    except OIDCError as exc:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error="provider_error",
            error_description=str(exc),
        )
    except UserAlreadyExistsError as exc:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error="account_conflict",
            error_description=str(exc),
        )
    except AuthenticationFailedError as exc:
        return oidc_frontend_redirect(
            settings=settings,
            redirect_to="/",
            error="account_disabled",
            error_description=str(exc),
        )

    return oidc_frontend_redirect(
        settings=settings,
        redirect_to=verified_state.redirect_to,
        token=token_response(user=user, service=service, settings=settings),
    )


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


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        result = await UserDeletionService(session=session, storage=storage).delete_user(
            admin_id=admin.id,
            user_id=user_id,
        )
    except InvalidUserDeletionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    for document_id in result.deleted_document_ids:
        await reindex_document_best_effort(
            session=session,
            settings=settings,
            document_id=document_id,
            reason="user_deleted",
        )


def token_response(*, user: User, service: IdentityService, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=service.create_access_token_for_user(user),
        expires_in_seconds=settings.jwt_access_token_minutes * 60,
        user=user_response(user),
    )


def require_oidc_redirect_uri(settings: Settings) -> str:
    if not settings.oidc_login_enabled or settings.oidc_redirect_uri is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC login is not configured",
        )
    return settings.oidc_redirect_uri


def oidc_frontend_redirect(
    *,
    settings: Settings,
    redirect_to: str,
    token: TokenResponse | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    fragment: dict[str, str] = {"redirect_to": redirect_to}
    if token is not None:
        fragment.update(
            {
                "access_token": token.access_token,
                "token_type": token.token_type,
                "expires_in": str(token.expires_in_seconds),
            },
        )
    if error is not None:
        fragment["error"] = error
        if error_description is not None:
            fragment["error_description"] = error_description

    location = f"{settings.web_app_url.rstrip('/')}/auth/oidc/callback#{urlencode(fragment)}"
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)


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
