import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from papervault_api.identity.domain.enums import UserRole

JWT_ALGORITHM = "HS256"


class TokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: UUID
    email: str
    role: UserRole
    expires_at: datetime


def create_access_token(
    *,
    subject: UUID,
    email: str,
    role: UserRole,
    signing_key: str,
    issuer: str,
    audience: str,
    ttl_minutes: int,
) -> str:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "email": email,
        "role": role.value,
        "iss": issuer,
        "aud": audience,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    signing_input = ".".join([_encode_json(header), _encode_json(payload)])
    signature = _sign(signing_input, signing_key)
    return f"{signing_input}.{_encode_bytes(signature)}"


def verify_access_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
    audience: str,
) -> AccessTokenClaims:
    try:
        header_text, payload_text, signature_text = token.split(".", 2)
    except ValueError as exc:
        raise TokenError("Malformed bearer token") from exc

    signing_input = f"{header_text}.{payload_text}"
    expected_signature = _sign(signing_input, signing_key)
    actual_signature = _decode_bytes(signature_text)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise TokenError("Invalid bearer token signature")

    header = _decode_json(header_text)
    if header.get("alg") != JWT_ALGORITHM:
        raise TokenError("Unsupported bearer token algorithm")

    payload = _decode_json(payload_text)
    if payload.get("iss") != issuer:
        raise TokenError("Invalid bearer token issuer")
    if payload.get("aud") != audience:
        raise TokenError("Invalid bearer token audience")

    expires_at = _timestamp_claim(payload, "exp")
    if expires_at <= datetime.now(UTC):
        raise TokenError("Bearer token has expired")

    try:
        subject = UUID(str(payload["sub"]))
        email = str(payload["email"])
        role = UserRole(str(payload["role"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("Bearer token is missing required claims") from exc

    return AccessTokenClaims(
        subject=subject,
        email=email,
        role=role,
        expires_at=expires_at,
    )


def _timestamp_claim(payload: dict[str, Any], key: str) -> datetime:
    try:
        timestamp = int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError(f"Bearer token is missing {key}") from exc
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _encode_json(value: dict[str, Any]) -> str:
    return _encode_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _decode_json(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_decode_bytes(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("Bearer token contains invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise TokenError("Bearer token payload must be an object")
    return decoded


def _sign(signing_input: str, signing_key: str) -> bytes:
    return hmac.new(
        signing_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except ValueError as exc:
        raise TokenError("Bearer token contains invalid base64") from exc
