import base64
import hashlib
import hmac
import secrets

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
SALT_BYTES = 16


class PasswordHashError(ValueError):
    pass


def hash_password(password: str, *, iterations: int) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive_password_hash(password=password, salt=salt, iterations=iterations)
    return "$".join(
        [
            PASSWORD_HASH_SCHEME,
            str(iterations),
            _encode_base64(salt),
            _encode_base64(digest),
        ],
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if scheme != PASSWORD_HASH_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = _decode_base64(salt_text)
        expected_digest = _decode_base64(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = _derive_password_hash(
        password=password,
        salt=salt,
        iterations=iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def _derive_password_hash(*, password: str, salt: bytes, iterations: int) -> bytes:
    if iterations < 100_000:
        raise PasswordHashError("Password hash iterations must be at least 100000")
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
