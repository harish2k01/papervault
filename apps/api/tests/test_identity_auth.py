import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.base import Base
from papervault_api.db.session import get_session
from papervault_api.main import create_app


def build_identity_test_app(
    settings_factory: Callable[[], Settings] | None = None,
) -> tuple[FastAPI, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    if settings_factory is not None:
        app.dependency_overrides[get_settings] = settings_factory

    return app, engine


def test_register_returns_token_and_first_user_is_admin() -> None:
    app, engine = build_identity_test_app(lambda: identity_test_settings())

    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "Owner@Example.com",
                "password": "correct horse battery staple",
                "display_name": "Owner",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "owner@example.com"
        assert body["user"]["role"] == "admin"

        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "owner@example.com"

    asyncio.run(engine.dispose())


def test_login_rejects_invalid_password_and_accepts_valid_password() -> None:
    app, engine = build_identity_test_app(lambda: identity_test_settings())

    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"email": "person@example.com", "password": "very strong password"},
        )

        invalid_response = client.post(
            "/auth/login",
            json={"email": "person@example.com", "password": "wrong"},
        )
        assert invalid_response.status_code == 401

        valid_response = client.post(
            "/auth/login",
            json={"email": "person@example.com", "password": "very strong password"},
        )
        assert valid_response.status_code == 200
        assert valid_response.json()["access_token"]

    asyncio.run(engine.dispose())


def test_admin_user_listing_requires_admin_role() -> None:
    app, engine = build_identity_test_app(lambda: identity_test_settings())

    with TestClient(app) as client:
        admin_token = register_and_get_token(client, "admin@example.com")
        user_token = register_and_get_token(client, "user@example.com")

        forbidden_response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert forbidden_response.status_code == 403

        list_response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_response.status_code == 200
        assert [user["email"] for user in list_response.json()] == [
            "admin@example.com",
            "user@example.com",
        ]

    asyncio.run(engine.dispose())


def test_dev_headers_can_be_disabled() -> None:
    app, engine = build_identity_test_app(
        lambda: identity_test_settings(auth_allow_dev_headers=False),
    )

    with TestClient(app) as client:
        response = client.get(
            "/auth/me",
            headers={"X-PaperVault-User-Id": "00000000-0000-0000-0000-000000000001"},
        )
        assert response.status_code == 401

    asyncio.run(engine.dispose())


def test_cannot_remove_last_active_admin() -> None:
    app, engine = build_identity_test_app(lambda: identity_test_settings())

    with TestClient(app) as client:
        admin_token = register_and_get_token(client, "admin@example.com")
        users_response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        admin_id = users_response.json()[0]["id"]

        response = client.patch(
            f"/users/{admin_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "user"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot remove the last active administrator"

    asyncio.run(engine.dispose())


def register_and_get_token(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


def identity_test_settings(**overrides: Any) -> Settings:
    return Settings(
        jwt_signing_key="test-signing-key",
        jwt_access_token_minutes=15,
        password_hash_iterations=100_000,
        **overrides,
    )
