import asyncio
import json
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt

from papervault_api.core.config import Settings
from papervault_api.identity.application.oidc import (
    OIDCClaims,
    OIDCConfigurationError,
    OIDCProviderError,
    OIDCTokenSet,
    OIDCTokenVerificationError,
)

OIDC_SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]


@dataclass(frozen=True, slots=True)
class DiscoveryDocument:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class HttpOIDCProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._discovery: DiscoveryDocument | None = None

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        redirect_uri: str,
    ) -> str:
        discovery = await self._discover()
        query = urlencode(
            {
                "client_id": self._client_id(),
                "response_type": "code",
                "scope": self._settings.oidc_scopes,
                "redirect_uri": redirect_uri,
                "state": state,
                "nonce": nonce,
            },
        )
        return f"{discovery.authorization_endpoint}?{query}"

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OIDCTokenSet:
        discovery = await self._discover()
        payload = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
            },
        ).encode("utf-8")
        request = Request(
            discovery.token_endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        response = await self._json_request(request)
        id_token = response.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCProviderError("OIDC provider did not return an ID token")

        access_token = response.get("access_token")
        expires_in = response.get("expires_in")
        return OIDCTokenSet(
            id_token=id_token,
            access_token=access_token if isinstance(access_token, str) else None,
            expires_in_seconds=expires_in if isinstance(expires_in, int) else None,
        )

    async def verify_id_token(
        self,
        *,
        id_token: str,
        nonce: str,
    ) -> OIDCClaims:
        discovery = await self._discover()

        try:
            jwk_client = jwt.PyJWKClient(
                discovery.jwks_uri,
                timeout=self._settings.oidc_http_timeout_seconds,
            )
            signing_key = await asyncio.to_thread(jwk_client.get_signing_key_from_jwt, id_token)
            decoded = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=OIDC_SIGNING_ALGORITHMS,
                audience=self._client_id(),
                issuer=discovery.issuer,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise OIDCTokenVerificationError("OIDC ID token verification failed") from exc

        claims = _ensure_mapping(decoded)
        token_nonce = claims.get("nonce")
        if token_nonce != nonce:
            raise OIDCTokenVerificationError("OIDC ID token nonce does not match")

        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or not subject:
            raise OIDCTokenVerificationError("OIDC ID token is missing subject")
        if not isinstance(email, str) or not email:
            raise OIDCTokenVerificationError("OIDC ID token is missing email")

        display_name = _first_string_claim(claims, "name", "preferred_username")
        return OIDCClaims(
            subject=subject,
            email=email,
            display_name=display_name,
        )

    async def _discover(self) -> DiscoveryDocument:
        if self._discovery is not None:
            return self._discovery

        issuer = self._issuer()
        discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        request = Request(discovery_url, headers={"Accept": "application/json"})
        document = await self._json_request(request)

        discovered_issuer = _required_discovery_string(document, "issuer")
        authorization_endpoint = _required_discovery_string(
            document,
            "authorization_endpoint",
        )
        token_endpoint = _required_discovery_string(document, "token_endpoint")
        jwks_uri = _required_discovery_string(document, "jwks_uri")

        if discovered_issuer.rstrip("/") != issuer.rstrip("/"):
            raise OIDCConfigurationError("OIDC discovery issuer does not match configuration")

        self._discovery = DiscoveryDocument(
            issuer=discovered_issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
        )
        return self._discovery

    async def _json_request(self, request: Request) -> dict[str, Any]:
        return await asyncio.to_thread(self._json_request_sync, request)

    def _json_request_sync(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(
                request,
                timeout=self._settings.oidc_http_timeout_seconds,
            ) as response:
                raw_body = response.read()
        except HTTPError as exc:
            raise OIDCProviderError(f"OIDC provider returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise OIDCProviderError("OIDC provider request failed") from exc

        try:
            decoded = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OIDCProviderError("OIDC provider returned invalid JSON") from exc
        return _ensure_mapping(decoded)

    def _issuer(self) -> str:
        issuer = self._settings.oidc_issuer_url
        if issuer is None:
            raise OIDCConfigurationError("OIDC issuer URL is not configured")
        return issuer

    def _client_id(self) -> str:
        client_id = self._settings.oidc_client_id
        if client_id is None:
            raise OIDCConfigurationError("OIDC client id is not configured")
        return client_id

    def _client_secret(self) -> str:
        client_secret = self._settings.oidc_client_secret
        if client_secret is None:
            raise OIDCConfigurationError("OIDC client secret is not configured")
        return client_secret


def _ensure_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OIDCProviderError("OIDC provider response must be a JSON object")
    return cast(dict[str, Any], value)


def _required_discovery_string(document: dict[str, Any], field_name: str) -> str:
    value = document.get(field_name)
    if not isinstance(value, str) or not value:
        raise OIDCConfigurationError(
            f"OIDC discovery document is missing {field_name}",
        )
    return value


def _first_string_claim(claims: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
