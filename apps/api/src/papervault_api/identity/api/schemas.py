from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from papervault_api.identity.domain.enums import AuthProvider, UserRole


class AuthConfigResponse(BaseModel):
    local_auth_enabled: bool
    local_registration_enabled: bool
    dev_headers_enabled: bool
    oidc_configured: bool


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AuthUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: UserRole
    auth_provider: AuthProvider
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: AuthUserResponse


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
