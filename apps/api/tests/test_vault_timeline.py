from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.infrastructure.models import Document
from papervault_api.identity.infrastructure.models import User
from papervault_api.timeline.application.read import VaultTimelineReadService
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent


async def test_vault_timeline_is_owner_scoped_and_includes_document_title(
    session: AsyncSession,
) -> None:
    owner = User(email="timeline-owner@example.com")
    other = User(email="timeline-other@example.com")
    session.add_all((owner, other))
    await session.flush()
    document = Document(
        owner_id=owner.id,
        title="Renewed policy",
        original_filename="policy.pdf",
        content_type="application/pdf",
        file_size_bytes=10,
        sha256_hash="c" * 64,
        storage_bucket="documents",
        storage_key="timeline/policy.pdf",
        status=DocumentStatus.READY.value,
        document_type="insurance_policy",
    )
    session.add(document)
    await session.flush()
    session.add_all(
        (
            TimelineEvent(
                owner_id=owner.id,
                actor_id=owner.id,
                document_id=document.id,
                event_type=TimelineEventType.VERSION_CREATED.value,
                payload={"version_number": 2},
            ),
            TimelineEvent(
                owner_id=other.id,
                actor_id=other.id,
                event_type=TimelineEventType.DOCUMENT_UPLOADED.value,
                payload={},
            ),
        )
    )
    await session.commit()

    events = await VaultTimelineReadService(session).list_events(
        owner_id=owner.id,
        limit=100,
        offset=0,
    )

    assert len(events) == 1
    assert events[0].document_id == document.id
    assert events[0].document_title == "Renewed policy"
    assert events[0].payload == {"version_number": 2}
