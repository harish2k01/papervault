import asyncio
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.base import Base
from papervault_api.db.session import get_session
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.infrastructure.models import Document
from papervault_api.main import create_app


def test_collection_api_supports_manual_and_dynamic_membership() -> None:
    app, engine, session_factory = build_test_app()
    user_id = uuid4()
    headers = dev_headers(user_id)
    with TestClient(app) as client:
        assert client.get("/collections", headers=headers).status_code == 200
        receipt_id = asyncio.run(
            create_document(
                session_factory,
                owner_id=user_id,
                title="Device receipt",
                document_type="receipt",
                issuer="Example Store",
            )
        )
        policy_id = asyncio.run(
            create_document(
                session_factory,
                owner_id=user_id,
                title="Coverage policy",
                document_type="insurance_policy",
                issuer="Example Insurance",
            )
        )

        manual = client.post(
            "/collections",
            headers=headers,
            json={
                "name": "Household",
                "kind": "manual",
                "view_mode": "grid",
                "rule": {},
            },
        )
        assert manual.status_code == 201
        collection_id = manual.json()["id"]
        added = client.post(
            f"/collections/{collection_id}/documents/{receipt_id}",
            headers=headers,
            json={},
        )
        page = client.get(
            f"/collections/{collection_id}/documents",
            headers=headers,
        )
        candidates = client.get(
            f"/collections/{collection_id}/candidates",
            headers=headers,
        )

        assert added.status_code == 200
        assert page.json()["total"] == 1
        assert page.json()["documents"][0]["id"] == str(receipt_id)
        assert candidates.json()["total"] == 1
        assert candidates.json()["documents"][0]["id"] == str(policy_id)

        dynamic = client.post(
            "/collections",
            headers=headers,
            json={
                "name": "Policies",
                "kind": "dynamic",
                "view_mode": "list",
                "rule": {
                    "document_types": ["insurance_policy"],
                    "issuer_contains": "example",
                },
            },
        )
        dynamic_page = client.get(
            f"/collections/{dynamic.json()['id']}/documents",
            headers=headers,
        )

        assert dynamic.status_code == 201
        assert dynamic.json()["document_count"] == 1
        assert dynamic_page.json()["documents"][0]["id"] == str(policy_id)

    asyncio.run(engine.dispose())


def test_smart_tag_api_materializes_and_refreshes_rule_matches() -> None:
    app, engine, session_factory = build_test_app()
    user_id = uuid4()
    headers = dev_headers(user_id)
    with TestClient(app) as client:
        assert client.get("/tags", headers=headers).status_code == 200
        document_id = asyncio.run(
            create_document(
                session_factory,
                owner_id=user_id,
                title="Current policy",
                document_type="insurance_policy",
                issuer="Example Insurance",
            )
        )
        created = client.post(
            "/tags/smart",
            headers=headers,
            json={
                "name": "Policies",
                "rule": {
                    "document_types": ["insurance_policy"],
                    "issuer_contains": "example",
                },
            },
        )
        tag_id = created.json()["id"]
        refreshed = client.post(
            f"/tags/{tag_id}/refresh",
            headers=headers,
            json={},
        )
        tags = client.get("/tags", headers=headers)

        assert created.status_code == 201
        assert created.json()["document_count"] == 1
        assert refreshed.status_code == 200
        assert refreshed.json()["matched"] == 1
        assert tags.json()[0]["smart_rule"]["document_types"] == [
            "insurance_policy"
        ]
        assert tags.json()[0]["document_count"] == 1
        assert tags.json()[0]["last_evaluated_at"] is not None
        assert document_id

    asyncio.run(engine.dispose())


def build_test_app() -> tuple[
    FastAPI,
    AsyncEngine,
    async_sessionmaker,
]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        search_index_enabled=False
    )
    return app, engine, session_factory


async def create_document(
    session_factory: async_sessionmaker,
    *,
    owner_id: UUID,
    title: str,
    document_type: str,
    issuer: str,
) -> UUID:
    identifier = uuid4()
    async with session_factory() as session:
        document = Document(
            owner_id=owner_id,
            title=title,
            original_filename=f"{identifier}.pdf",
            content_type="application/pdf",
            file_size_bytes=256,
            sha256_hash=identifier.hex * 2,
            storage_bucket="documents",
            storage_key=f"{identifier}.pdf",
            status=DocumentStatus.READY.value,
            document_type=document_type,
            issuer=issuer,
        )
        session.add(document)
        await session.commit()
        return document.id


def dev_headers(user_id: UUID) -> dict[str, str]:
    return {
        "X-PaperVault-User-Id": str(user_id),
        "X-PaperVault-User-Email": "owner@example.test",
    }
