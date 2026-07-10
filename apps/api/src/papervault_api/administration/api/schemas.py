from pydantic import BaseModel


class AdminSettingsResponse(BaseModel):
    local_registration_enabled: bool
    local_auth_enabled: bool
    oidc_configured: bool
    ai_provider: str
    embedding_provider: str
    ocr_provider: str
    search_backend: str
    search_index_enabled: bool
    max_upload_size_bytes: int


class UpdateAdminSettingsRequest(BaseModel):
    local_registration_enabled: bool
