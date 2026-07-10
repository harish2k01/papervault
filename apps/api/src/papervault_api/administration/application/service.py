from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.administration.infrastructure.models import InstanceSettings
from papervault_api.core.config import Settings


@dataclass(frozen=True, slots=True)
class EffectiveInstanceSettings:
    local_registration_enabled: bool


class InstanceSettingsService:
    def __init__(self, session: AsyncSession, runtime_settings: Settings) -> None:
        self._session = session
        self._runtime_settings = runtime_settings

    async def get_effective(self) -> EffectiveInstanceSettings:
        persisted = await self._session.get(InstanceSettings, 1)
        return EffectiveInstanceSettings(
            local_registration_enabled=(
                persisted.local_registration_enabled
                if persisted is not None
                else self._runtime_settings.local_registration_enabled
            )
        )

    async def update(
        self,
        *,
        local_registration_enabled: bool,
        updated_by_id: UUID,
    ) -> EffectiveInstanceSettings:
        persisted = await self._session.get(InstanceSettings, 1)
        if persisted is None:
            persisted = InstanceSettings(
                id=1,
                local_registration_enabled=local_registration_enabled,
                updated_by_id=updated_by_id,
            )
            self._session.add(persisted)
        else:
            persisted.local_registration_enabled = local_registration_enabled
            persisted.updated_by_id = updated_by_id
        await self._session.commit()
        return EffectiveInstanceSettings(
            local_registration_enabled=local_registration_enabled,
        )
