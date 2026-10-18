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
    enrichment_queue_enabled: bool = Field(
        default=False, alias="PAPERVAULT_ENRICHMENT_QUEUE_ENABLED"
    )
    ai_provider: str = Field(default="local", alias="PAPERVAULT_AI_PROVIDER")
    answer_provider: str = Field(default="local", alias="PAPERVAULT_ANSWER_PROVIDER")
    embedding_provider: str = Field(default="local", alias="PAPERVAULT_EMBEDDING_PROVIDER")
    embedding_dimensions: int = Field(default=64, alias="PAPERVAULT_EMBEDDING_DIMENSIONS")
    rag_mode: str = Field(default="disabled", alias="PAPERVAULT_RAG_MODE")
    rag_chat_model: str | None = Field(default=None, alias="PAPERVAULT_RAG_CHAT_MODEL")
    rag_chat_digest: str | None = Field(default=None, alias="PAPERVAULT_RAG_CHAT_DIGEST")
    rag_embeddings_url: str = Field(
        default="http://localhost:8081", alias="PAPERVAULT_RAG_EMBEDDINGS_URL"
    )
    rag_reranker_url: str = Field(
        default="http://localhost:8082", alias="PAPERVAULT_RAG_RERANKER_URL"
    )
    rag_parser_url: str = Field(default="http://localhost:5001", alias="PAPERVAULT_RAG_PARSER_URL")
    rag_embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5", alias="PAPERVAULT_RAG_EMBEDDING_MODEL"
    )
    rag_embedding_revision: str = Field(
        default="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        alias="PAPERVAULT_RAG_EMBEDDING_REVISION",
    )
    rag_dimensions: int = Field(default=384, ge=1, alias="PAPERVAULT_RAG_DIMENSIONS")
    rag_reranker_model: str = Field(
        default="BAAI/bge-reranker-base", alias="PAPERVAULT_RAG_RERANKER_MODEL"
    )
    rag_reranker_revision: str = Field(
        default="2cfc18c9415c912f9d8155881c133215df768a70", alias="PAPERVAULT_RAG_RERANKER_REVISION"
    )
    # A relevance score is not a probability of truth. Calibrate this gate on held-out cases.
    rag_min_rerank_score: float = Field(
        default=0.0, ge=0, le=1, alias="PAPERVAULT_RAG_MIN_RERANK_SCORE"
    )

    @field_validator("rag_mode")
    @classmethod
    def validate_rag_mode(cls, value: str) -> str:
        if value not in {"disabled", "preview", "enabled"}:
            raise ValueError("RAG mode must be disabled, preview, or enabled")
        return value

    @field_validator("rag_embeddings_url", "rag_reranker_url", "rag_parser_url")
    @classmethod
    def validate_private_inference_url(cls, value: str) -> str:
        from ipaddress import ip_address
        from urllib.parse import urlsplit

        url = urlsplit(value)
        host = url.hostname or ""
        allowed = (
            host == "localhost"
            or host.endswith((".svc", ".svc.cluster.local"))
            or (host.startswith("papervault-") and "." not in host)
        )
        try:
            address = ip_address(host)
            allowed = (address.is_private or address.is_loopback) and not address.is_link_local
        except ValueError:
            pass
        if (
            not allowed
            or url.scheme not in {"http", "https"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Structured processing requires a private inference service URL")
        return value.rstrip("/")

    ai_classification_threshold: float = Field(
        default=0.55,
        alias="PAPERVAULT_AI_CLASSIFICATION_THRESHOLD",
    )
    duplicate_content_similarity_threshold: float = Field(
        default=0.88,
        ge=0.5,
        le=1.0,
        alias="PAPERVAULT_DUPLICATE_CONTENT_SIMILARITY_THRESHOLD",
    )
    duplicate_ocr_similarity_threshold: float = Field(
        default=0.84,
        ge=0.5,
        le=1.0,
        alias="PAPERVAULT_DUPLICATE_OCR_SIMILARITY_THRESHOLD",
    )
    duplicate_similarity_min_tokens: int = Field(
        default=24,
        ge=12,
        le=500,
        alias="PAPERVAULT_DUPLICATE_SIMILARITY_MIN_TOKENS",
    )
    metadata_locale: str = Field(default="en-IN", alias="PAPERVAULT_METADATA_LOCALE")
    model_provider_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        alias="PAPERVAULT_MODEL_PROVIDER_TIMEOUT_SECONDS",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="PAPERVAULT_OLLAMA_BASE_URL",
    )
    ollama_chat_model: str = Field(
        default="llama3.2",
        alias="PAPERVAULT_OLLAMA_CHAT_MODEL",
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        alias="PAPERVAULT_OLLAMA_EMBEDDING_MODEL",
    )
    ollama_context_tokens: int = Field(
        default=16384, ge=4096, le=65536, alias="PAPERVAULT_OLLAMA_CONTEXT_TOKENS"
    )
    ollama_max_output_tokens: int = Field(
        default=2048, ge=256, le=8192, alias="PAPERVAULT_OLLAMA_MAX_OUTPUT_TOKENS"
    )
    ollama_expected_digest: str | None = Field(
        default=None, alias="PAPERVAULT_OLLAMA_EXPECTED_DIGEST"
    )
    openai_compatible_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="PAPERVAULT_OPENAI_COMPATIBLE_BASE_URL",
    )
    openai_compatible_api_key: str | None = Field(
        default=None,
        alias="PAPERVAULT_OPENAI_COMPATIBLE_API_KEY",
    )
    openai_compatible_chat_model: str = Field(
        default="gpt-4.1-mini",
        alias="PAPERVAULT_OPENAI_COMPATIBLE_CHAT_MODEL",
    )
    openai_compatible_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="PAPERVAULT_OPENAI_COMPATIBLE_EMBEDDING_MODEL",
    )
    ocr_provider: str = Field(default="tesseract", alias="PAPERVAULT_OCR_PROVIDER")
    ocr_languages: str = Field(default="eng", alias="PAPERVAULT_OCR_LANGUAGES")
    ocr_timeout_seconds: int = Field(default=120, ge=1, alias="PAPERVAULT_OCR_TIMEOUT_SECONDS")
    ocr_pdf_dpi: int = Field(default=200, ge=72, le=600, alias="PAPERVAULT_OCR_PDF_DPI")
    ocr_max_pdf_pages: int | None = Field(
        default=50,
        ge=1,
        alias="PAPERVAULT_OCR_MAX_PDF_PAGES",
    )
    ocr_tesseract_command: str = Field(default="tesseract", alias="PAPERVAULT_TESSERACT_CMD")
    ocr_pdftoppm_command: str = Field(default="pdftoppm", alias="PAPERVAULT_PDFTOPPM_CMD")
    ocr_tesseract_psm: int = Field(default=6, ge=0, le=13, alias="PAPERVAULT_TESSERACT_PSM")

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
    search_index_enabled: bool = Field(default=True, alias="PAPERVAULT_SEARCH_INDEX_ENABLED")
    search_query_backend: str = Field(
        default="opensearch",
        alias="PAPERVAULT_SEARCH_QUERY_BACKEND",
    )
    search_query_fallback_enabled: bool = Field(
        default=True,
        alias="PAPERVAULT_SEARCH_QUERY_FALLBACK_ENABLED",
    )
    opensearch_documents_index: str = Field(
        default="papervault-documents-v1",
        alias="OPENSEARCH_DOCUMENTS_INDEX",
    )
    opensearch_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        alias="OPENSEARCH_TIMEOUT_SECONDS",
    )

    oidc_issuer_url: str | None = Field(default=None, alias="OIDC_ISSUER_URL")
    oidc_client_id: str | None = Field(default=None, alias="OIDC_CLIENT_ID")
    oidc_client_secret: str | None = Field(default=None, alias="OIDC_CLIENT_SECRET")
    oidc_redirect_uri: str | None = Field(default=None, alias="OIDC_REDIRECT_URI")
    oidc_scopes: str = Field(default="openid email profile", alias="OIDC_SCOPES")
    oidc_state_ttl_seconds: int = Field(default=600, ge=60, alias="OIDC_STATE_TTL_SECONDS")
    oidc_http_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        alias="OIDC_HTTP_TIMEOUT_SECONDS",
    )
    web_app_url: str = Field(default="http://localhost:5173", alias="PAPERVAULT_WEB_APP_URL")
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
        "oidc_redirect_uri",
        "otel_exporter_otlp_endpoint",
        "openai_compatible_api_key",
        "ollama_expected_digest",
        "rag_chat_model",
        "rag_chat_digest",
        "ocr_max_pdf_pages",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator("search_query_backend", mode="before")
    @classmethod
    def validate_search_query_backend(cls, value: Any) -> str:
        backend = str(value or "opensearch").strip().lower()
        if backend not in {"database", "opensearch"}:
            raise ValueError("Search query backend must be 'database' or 'opensearch'")
        return backend

    @field_validator("ai_provider", "answer_provider", "embedding_provider", mode="before")
    @classmethod
    def validate_model_provider(cls, value: Any) -> str:
        provider = str(value or "local").strip().lower().replace("-", "_")
        if provider not in {"local", "ollama", "openai_compatible"}:
            raise ValueError("Model provider must be 'local', 'ollama', or 'openai_compatible'")
        return provider

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

    @property
    def oidc_login_enabled(self) -> bool:
        return bool(
            self.oidc_issuer_url
            and self.oidc_client_id
            and self.oidc_client_secret
            and self.oidc_redirect_uri
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
