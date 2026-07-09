import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class OIDCStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreatedOIDCState:
    token: str
    nonce: str
    redirect_to: str


@dataclass(frozen=True, slots=True)
class VerifiedOIDCState:
    nonce: str
    redirect_to: str


def create_oidc_state(
    *,
    signing_key: str,
    redirect_to: str | None,
    ttl_seconds: int,
) -> CreatedOIDCState:
    sanitized_redirect = sanitize_redirect_path(redirect_to)
    nonce = secrets.token_urlsafe(32)
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload = {
        "nonce": nonce,
        "redirect_to": sanitized_redirect,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload_text = _encode_json(payload)
    signature = _sign(payload_text, signing_key)
    return CreatedOIDCState(
        token=f"{payload_text}.{_encode_bytes(signature)}",
        nonce=nonce,
        redirect_to=sanitized_redirect,
    )


def verify_oidc_state(*, token: str, signing_key: str) -> VerifiedOIDCState:
    try:
        payload_text, signature_text = token.split(".", 1)
    except ValueError as exc:
        raise OIDCStateError("Malformed OIDC state") from exc

    expected_signature = _sign(payload_text, signing_key)
    actual_signature = _decode_bytes(signature_text)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise OIDCStateError("Invalid OIDC state signature")

    payload = _decode_json(payload_text)
    expires_at = _timestamp_claim(payload, "exp")
    if expires_at <= datetime.now(UTC):
        raise OIDCStateError("OIDC state has expired")

    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise OIDCStateError("OIDC state is missing nonce")

    redirect_to = payload.get("redirect_to")
    if not isinstance(redirect_to, str):
        raise OIDCStateError("OIDC state is missing redirect target")

    return VerifiedOIDCState(
        nonce=nonce,
        redirect_to=sanitize_redirect_path(redirect_to),
    )


def sanitize_redirect_path(value: str | None) -> str:
    if not value:
        return "/"

    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        raise OIDCStateError("OIDC redirect target must be a same-origin path")
    if parts.path.startswith("//") or "\\" in parts.path:
        raise OIDCStateError("OIDC redirect target must be a same-origin path")

    return urlunsplit(("", "", parts.path, parts.query, ""))


def _timestamp_claim(payload: dict[str, Any], key: str) -> datetime:
    try:
        timestamp = int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise OIDCStateError(f"OIDC state is missing {key}") from exc
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _encode_json(value: dict[str, Any]) -> str:
    return _encode_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _decode_json(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_decode_bytes(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OIDCStateError("OIDC state contains invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise OIDCStateError("OIDC state payload must be an object")
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
        raise OIDCStateError("OIDC state contains invalid base64") from exc
