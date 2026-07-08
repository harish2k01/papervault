from enum import StrEnum


class AuthProvider(StrEnum):
    LOCAL = "local"
    OIDC = "oidc"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"
