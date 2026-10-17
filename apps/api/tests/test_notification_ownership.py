import asyncio
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_collections_api import build_test_app, create_document, dev_headers

from papervault_api.documents.infrastructure.models import DocumentMetadataRecord
from papervault_api.notifications.infrastructure.models import Notification


def test_reminder_refresh_checks_ownership_before_creating_or_dismissing_records() -> None:
    app, engine, factory = build_test_app()
    owner_id = uuid4()
    owner = dev_headers(owner_id)
    other = {**dev_headers(uuid4()), "X-PaperVault-User-Email": "other@example.test"}

    async def set_expiry(document_id, expiry):
        async with factory() as session:
            metadata = await session.scalar(
                select(DocumentMetadataRecord).where(
                    DocumentMetadataRecord.document_id == document_id,
                )
            )
            if metadata is None:
                session.add(
                    DocumentMetadataRecord(
                        document_id=document_id,
                        schema_name="insurance_policy",
                        schema_version=1,
                        data={"expiry_date": expiry},
                        source="manual",
                        is_current=True,
                    )
                )
            else:
                metadata.data = {"expiry_date": expiry}
            await session.commit()

    async def stored_reminders():
        async with factory() as session:
            return [
                (item.due_date, item.status) for item in await session.scalars(select(Notification))
            ]

    with TestClient(app) as client:
        assert client.get("/notifications", headers=owner).status_code == 200
        document_id = asyncio.run(
            create_document(
                factory,
                owner_id=owner_id,
                title="Policy",
                document_type="insurance_policy",
                issuer="Example",
            )
        )
        asyncio.run(set_expiry(document_id, "2027-01-01"))
        endpoint = f"/notifications/sync/{document_id}"
        assert client.post(endpoint, headers=other).status_code == 404
        assert client.post(f"/notifications/sync/{uuid4()}", headers=other).status_code == 404
        assert asyncio.run(stored_reminders()) == []
        response = client.post(endpoint, headers=owner)
        assert response.status_code == 200 and len(response.json()) == 1
        original = asyncio.run(stored_reminders())
        assert original == [(date(2027, 1, 1), "pending")]
        asyncio.run(set_expiry(document_id, "2027-02-01"))
        assert client.post(endpoint, headers=other).status_code == 404
        assert asyncio.run(stored_reminders()) == original
    asyncio.run(engine.dispose())
