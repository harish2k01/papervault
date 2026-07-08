from dataclasses import dataclass
from uuid import UUID

from papervault_api.identity.domain.enums import UserRole


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    role: UserRole
