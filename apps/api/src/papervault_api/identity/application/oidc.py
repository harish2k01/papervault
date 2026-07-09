from dataclasses import dataclass
from typing import Protocol


class OIDCError(ValueError):
    pass


class OIDCConfigurationError(OIDCError):
    pass


class OIDCProviderError(OIDCError):
    pass


class OIDCTokenVerificationError(OIDCError):
    pass


@dataclass(frozen=True, slots=True)
class OIDCTokenSet:
    id_token: str
    access_token: str | None = None
    expires_in_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class OIDCClaims:
    subject: str
    email: str
    display_name: str | None = None


class OIDCProvider(Protocol):
    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        redirect_uri: str,
    ) -> str:
        pass

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OIDCTokenSet:
        pass

    async def verify_id_token(
        self,
        *,
        id_token: str,
        nonce: str,
    ) -> OIDCClaims:
        pass
