from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from papervault_api.core.config import Settings, get_settings

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_settings)]


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


@router.get("/health/live", response_model=HealthResponse)
async def liveness(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )
