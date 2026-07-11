import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.administration.api.schemas import (
    AdminSettingsResponse,
    ProviderHealthCheckResponse,
    ProviderHealthResponse,
    UpdateAdminSettingsRequest,
)
from papervault_api.administration.application.service import InstanceSettingsService
from papervault_api.core.config import Settings, get_settings
from papervault_api.core.model_clients import build_model_client
from papervault_api.db.session import get_session
from papervault_api.identity.api.dependencies import require_roles
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.domain.enums import UserRole

router = APIRouter(prefix="/admin/settings", tags=["administration"])


@router.get("/providers/health", response_model=ProviderHealthResponse)
async def get_provider_health(
    _admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProviderHealthResponse:
    configurations = (
        ("Analysis", settings.ai_provider, model_name(settings.ai_provider, settings, False)),
        (
            "Embeddings",
            settings.embedding_provider,
            model_name(settings.embedding_provider, settings, True),
        ),
        (
            "Answers",
            settings.answer_provider,
            model_name(settings.answer_provider, settings, False),
        ),
    )
    health_by_provider: dict[str, tuple[bool, str]] = {"local": (True, "Built-in provider")}
    for provider in {item[1] for item in configurations} - {"local"}:
        client = build_model_client(provider, settings, timeout_seconds=5.0)
        health_by_provider[provider] = await asyncio.to_thread(client.health)

    return ProviderHealthResponse(
        checks=[
            ProviderHealthCheckResponse(
                capability=capability,
                provider=provider,
                model=model,
                healthy=health_by_provider[provider][0],
                detail=health_by_provider[provider][1],
            )
            for capability, provider, model in configurations
        ]
    )


@router.get("", response_model=AdminSettingsResponse)
async def get_admin_settings(
    _admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminSettingsResponse:
    effective = await InstanceSettingsService(session, settings).get_effective()
    return admin_settings_response(settings, effective.local_registration_enabled)


@router.patch("", response_model=AdminSettingsResponse)
async def update_admin_settings(
    request: UpdateAdminSettingsRequest,
    admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminSettingsResponse:
    effective = await InstanceSettingsService(session, settings).update(
        local_registration_enabled=request.local_registration_enabled,
        updated_by_id=admin.id,
    )
    return admin_settings_response(settings, effective.local_registration_enabled)


def admin_settings_response(
    settings: Settings,
    local_registration_enabled: bool,
) -> AdminSettingsResponse:
    return AdminSettingsResponse(
        local_registration_enabled=local_registration_enabled,
        local_auth_enabled=settings.local_auth_enabled,
        oidc_configured=settings.oidc_login_enabled,
        ai_provider=settings.ai_provider,
        answer_provider=settings.answer_provider,
        embedding_provider=settings.embedding_provider,
        ocr_provider=settings.ocr_provider,
        search_backend=settings.search_query_backend,
        search_index_enabled=settings.search_index_enabled,
        max_upload_size_bytes=settings.max_upload_size_bytes,
    )


def model_name(provider: str, settings: Settings, embedding: bool) -> str:
    if provider == "local":
        return f"hashing-{settings.embedding_dimensions}" if embedding else "rules-v1"
    if provider == "ollama":
        return settings.ollama_embedding_model if embedding else settings.ollama_chat_model
    if provider == "openai_compatible":
        return (
            settings.openai_compatible_embedding_model
            if embedding
            else settings.openai_compatible_chat_model
        )
    return "unknown"
