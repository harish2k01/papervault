from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.application.oidc import OIDCClaims
from papervault_api.identity.application.passwords import hash_password, verify_password
from papervault_api.identity.application.tokens import create_access_token
from papervault_api.identity.domain.enums import AuthProvider, UserRole
from papervault_api.identity.infrastructure.models import User

MIN_PASSWORD_LENGTH = 12


class IdentityError(ValueError):
    pass


class AuthenticationFailedError(IdentityError):
    pass


class LocalAuthDisabledError(IdentityError):
    pass


class RegistrationDisabledError(IdentityError):
    pass


class UserAlreadyExistsError(IdentityError):
    pass


class WeakPasswordError(IdentityError):
    pass


class IdentityService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def register_local_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None,
    ) -> User:
        if not self._settings.local_auth_enabled:
            raise LocalAuthDisabledError("Local authentication is disabled")
        if not self._settings.local_registration_enabled:
            raise RegistrationDisabledError("Local registration is disabled")
        self._validate_password(password)

        normalized_email = normalize_email(email)
        existing = await self.get_user_by_email(normalized_email)
        if existing is not None:
            raise UserAlreadyExistsError("A user with this email already exists")

        role = UserRole.ADMIN if await self._is_first_user() else UserRole.USER
        user = User(
            email=normalized_email,
            display_name=display_name,
            auth_provider=AuthProvider.LOCAL.value,
            password_hash=hash_password(
                password,
                iterations=self._settings.password_hash_iterations,
            ),
            role=role.value,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def authenticate_local_user(self, *, email: str, password: str) -> User:
        if not self._settings.local_auth_enabled:
            raise LocalAuthDisabledError("Local authentication is disabled")

        user = await self.get_user_by_email(normalize_email(email))
        if user is None or user.password_hash is None:
            raise AuthenticationFailedError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationFailedError("User account is disabled")
        if not verify_password(password, user.password_hash):
            raise AuthenticationFailedError("Invalid email or password")

        user.last_login_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def authenticate_oidc_user(self, *, claims: OIDCClaims) -> User:
        normalized_email = normalize_email(claims.email)
        now = datetime.now(UTC)

        result = await self._session.execute(
            select(User).where(
                User.auth_provider == AuthProvider.OIDC.value,
                User.external_subject == claims.subject,
            ),
        )
        user = result.scalar_one_or_none()
        if user is not None:
            if not user.is_active:
                raise AuthenticationFailedError("User account is disabled")
            if user.email != normalized_email:
                existing_user = await self.get_user_by_email(normalized_email)
                if existing_user is not None and existing_user.id != user.id:
                    raise UserAlreadyExistsError("A user with this email already exists")
                user.email = normalized_email
            user.display_name = normalize_display_name(claims.display_name) or user.display_name
            user.last_login_at = now
            await self._session.commit()
            await self._session.refresh(user)
            return user

        existing_user = await self.get_user_by_email(normalized_email)
        if existing_user is not None:
            raise UserAlreadyExistsError("A user with this email already exists")

        role = UserRole.ADMIN if await self._is_first_user() else UserRole.USER
        user = User(
            email=normalized_email,
            display_name=normalize_display_name(claims.display_name),
            auth_provider=AuthProvider.OIDC.value,
            external_subject=claims.subject,
            password_hash=None,
            role=role.value,
            last_login_at=now,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == normalize_email(email)),
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list_users(self) -> list[User]:
        result = await self._session.execute(select(User).order_by(User.created_at))
        return list(result.scalars().all())

    async def update_user(
        self,
        *,
        user_id: UUID,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        user = await self.get_user_by_id(user_id)
        if user is None:
            return None
        if display_name is not None:
            user.display_name = display_name
        if role is not None:
            user.role = role.value
        if is_active is not None:
            user.is_active = is_active
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def count_active_admins(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN.value,
                User.is_active.is_(True),
            ),
        )
        return result.scalar_one()

    def create_access_token_for_user(self, user: User) -> str:
        return create_access_token(
            subject=user.id,
            email=user.email,
            role=UserRole(user.role),
            signing_key=self._settings.jwt_signing_key,
            issuer=self._settings.jwt_issuer,
            audience=self._settings.jwt_audience,
            ttl_minutes=self._settings.jwt_access_token_minutes,
        )

    async def _is_first_user(self) -> bool:
        result = await self._session.execute(select(func.count()).select_from(User))
        return result.scalar_one() == 0

    def _validate_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters long",
            )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_display_name(display_name: str | None) -> str | None:
    if display_name is None:
        return None
    stripped = display_name.strip()
    if not stripped:
        return None
    return stripped[:120]


def current_user_from_model(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
    )
