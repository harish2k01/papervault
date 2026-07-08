from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = Field(default="papervault-api", alias="PAPERVAULT_SERVICE_NAME")
    environment: str = Field(default="development", alias="PAPERVAULT_ENV")
    log_level: str = Field(default="INFO", alias="PAPERVAULT_LOG_LEVEL")
    api_cors_origins: str = Field(
        default="http://localhost:5173",
        alias="PAPERVAULT_API_CORS_ORIGINS",
    )
    max_upload_size_bytes: int = Field(
        default=100 * 1024 * 1024,
        alias="PAPERVAULT_MAX_UPLOAD_SIZE_BYTES",
    )
    ai_enabled: bool = Field(default=True, alias="PAPERVAULT_AI_ENABLED")
    ai_provider: str = Field(default="local", alias="PAPERVAULT_AI_PROVIDER")
    embedding_provider: str = Field(default="local", alias="PAPERVAULT_EMBEDDING_PROVIDER")
    embedding_dimensions: int = Field(default=64, alias="PAPERVAULT_EMBEDDING_DIMENSIONS")
    ai_classification_threshold: float = Field(
        default=0.55,
        alias="PAPERVAULT_AI_CLASSIFICATION_THRESHOLD",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://papervault:papervault@localhost:5432/papervault",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    s3_endpoint_url: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(default="papervault", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="papervault-secret", alias="S3_SECRET_ACCESS_KEY")
    s3_bucket_documents: str = Field(default="documents", alias="S3_BUCKET_DOCUMENTS")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")
    opensearch_username: str | None = Field(default=None, alias="OPENSEARCH_USERNAME")
    opensearch_password: str | None = Field(default=None, alias="OPENSEARCH_PASSWORD")

    oidc_issuer_url: str | None = Field(default=None, alias="OIDC_ISSUER_URL")
    oidc_client_id: str | None = Field(default=None, alias="OIDC_CLIENT_ID")
    oidc_client_secret: str | None = Field(default=None, alias="OIDC_CLIENT_SECRET")
    jwt_signing_key: str = Field(default="change-me-in-production", alias="JWT_SIGNING_KEY")
    jwt_issuer: str = Field(default="papervault", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="papervault-web", alias="JWT_AUDIENCE")
    jwt_access_token_minutes: int = Field(default=60, alias="JWT_ACCESS_TOKEN_MINUTES")
    local_auth_enabled: bool = Field(default=True, alias="PAPERVAULT_LOCAL_AUTH_ENABLED")
    local_registration_enabled: bool = Field(
        default=True,
        alias="PAPERVAULT_LOCAL_REGISTRATION_ENABLED",
    )
    auth_allow_dev_headers: bool = Field(default=True, alias="PAPERVAULT_AUTH_ALLOW_DEV_HEADERS")
    password_hash_iterations: int = Field(
        default=600_000,
        ge=100_000,
        alias="PAPERVAULT_PASSWORD_HASH_ITERATIONS",
    )

    otel_service_name: str = Field(default="papervault-api", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )

    @field_validator(
        "opensearch_username",
        "opensearch_password",
        "oidc_issuer_url",
        "oidc_client_id",
        "oidc_client_secret",
        "otel_exporter_otlp_endpoint",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.api_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def dev_auth_enabled(self) -> bool:
        return self.auth_allow_dev_headers and self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
