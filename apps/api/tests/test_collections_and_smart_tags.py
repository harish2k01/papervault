from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.collections.application.service import (
    CollectionService,
    InvalidCollectionOperationError,
)
from papervault_api.collections.domain.enums import CollectionKind
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.domain.rules import DocumentRule
from papervault_api.documents.infrastructure.models import Document
from papervault_api.identity.infrastructure.models import User
from papervault_api.tags.application.service import InvalidSmartTagRuleError, TagService
from papervault_api.tags.domain.enums import TagSource
from papervault_api.tags.infrastructure.models import DocumentTag
from papervault_api.timeline.infrastructure.models import TimelineEvent


async def test_manual_collection_membership_is_owner_scoped(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, "owner@example.test")
    other_owner = await create_user(session, "other@example.test")
    document = await create_document(
        session,
        owner_id=owner.id,
        title="Purchase receipt",
        document_type="receipt",
    )
    foreign_document = await create_document(
        session,
        owner_id=other_owner.id,
        title="Foreign receipt",
        document_type="receipt",
    )
    service = CollectionService(session)
    summary = await service.create_collection(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Household",
        kind=CollectionKind.MANUAL,
    )

    assert (
        await service.add_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=document.id,
        )
        is True
    )
    assert (
        await service.add_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=document.id,
        )
        is False
    )
    assert (
        await service.add_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=foreign_document.id,
        )
        is None
    )

    page = await service.list_documents(
        owner_id=owner.id,
        collection_id=summary.collection.id,
    )
    assert page is not None
    assert page.total == 1
    assert page.documents == (document,)

    assert (
        await service.remove_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=document.id,
        )
        is True
    )
    assert (
        await service.remove_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=document.id,
        )
        is False
    )


async def test_dynamic_collection_evaluates_typed_rule_without_materializing_membership(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, "dynamic@example.test")
    matching = await create_document(
        session,
        owner_id=owner.id,
        title="Device invoice",
        document_type="invoice",
        organization="Example Store",
        document_date=date(2026, 5, 1),
    )
    await create_document(
        session,
        owner_id=owner.id,
        title="Older device invoice",
        document_type="invoice",
        organization="Example Store",
        document_date=date(2024, 5, 1),
    )
    await create_document(
        session,
        owner_id=owner.id,
        title="Medical report",
        document_type="medical_report",
        organization="Example Store",
        document_date=date(2026, 5, 1),
    )
    service = CollectionService(session)
    summary = await service.create_collection(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Recent purchases",
        kind=CollectionKind.DYNAMIC,
        rule=DocumentRule(
            document_types=("invoice",),
            organization_contains="example",
            date_from=date(2026, 1, 1),
        ),
    )

    page = await service.list_documents(
        owner_id=owner.id,
        collection_id=summary.collection.id,
    )
    assert summary.document_count == 1
    assert page is not None
    assert page.total == 1
    assert page.documents == (matching,)
    with pytest.raises(InvalidCollectionOperationError):
        await service.add_document(
            owner_id=owner.id,
            actor_id=owner.id,
            collection_id=summary.collection.id,
            document_id=matching.id,
        )


async def test_dynamic_collection_can_follow_existing_tags(session: AsyncSession) -> None:
    owner = await create_user(session, "tagged-collection@example.test")
    tagged = await create_document(session, owner_id=owner.id, title="Tagged policy")
    untagged = await create_document(session, owner_id=owner.id, title="Untagged policy")
    tag_service = TagService(session)
    tag = await tag_service.create_tag(owner_id=owner.id, name="Renewal")
    await tag_service.attach_tag(owner_id=owner.id, document_id=tagged.id, tag_id=tag.id)

    summary = await CollectionService(session).create_collection(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Renewals",
        kind=CollectionKind.DYNAMIC,
        rule=DocumentRule(tags_any=("renewal",)),
    )
    page = await CollectionService(session).list_documents(
        owner_id=owner.id,
        collection_id=summary.collection.id,
    )

    assert page is not None
    assert page.documents == (tagged,)
    assert untagged not in page.documents


async def test_smart_tag_refresh_and_document_sync_preserve_manual_precedence(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, "smart-tags@example.test")
    matching = await create_document(
        session,
        owner_id=owner.id,
        title="Policy document",
        document_type="insurance_policy",
        issuer="Example Insurance",
    )
    other = await create_document(
        session,
        owner_id=owner.id,
        title="General note",
        document_type="generic_pdf",
    )
    service = TagService(session)
    tag, refresh = await service.create_smart_tag(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Insurance",
        rule=DocumentRule(
            document_types=("insurance_policy",),
            issuer_contains="example",
        ),
    )

    link = await session.get(
        DocumentTag,
        {"document_id": matching.id, "tag_id": tag.id},
    )
    assert refresh.evaluated == 2
    assert refresh.matched == 1
    assert refresh.attached == 1
    assert link is not None
    assert link.source == TagSource.SMART.value

    await service.attach_tag(owner_id=owner.id, document_id=matching.id, tag_id=tag.id)
    matching.issuer = "Different Provider"
    other.document_type = "insurance_policy"
    other.issuer = "Example Insurance"
    await session.commit()

    changed = await service.synchronize_document(
        owner_id=owner.id,
        document_id=matching.id,
        actor_id=owner.id,
    )
    await service.synchronize_document(
        owner_id=owner.id,
        document_id=other.id,
        actor_id=None,
    )
    manual_link = await session.get(
        DocumentTag,
        {"document_id": matching.id, "tag_id": tag.id},
    )
    automatic_link = await session.get(
        DocumentTag,
        {"document_id": other.id, "tag_id": tag.id},
    )
    events = tuple(
        (
            await session.execute(
                select(TimelineEvent).where(TimelineEvent.document_id.in_((matching.id, other.id))),
            )
        ).scalars()
    )

    assert changed == ()
    assert manual_link is not None
    assert manual_link.source == TagSource.MANUAL.value
    assert automatic_link is not None
    assert automatic_link.source == TagSource.SMART.value
    assert any(event.payload.get("action") == "smart_tag_attached" for event in events)


async def test_smart_tag_sync_removes_only_smart_assignments(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, "smart-removal@example.test")
    document = await create_document(
        session,
        owner_id=owner.id,
        title="Current invoice",
        document_type="invoice",
    )
    service = TagService(session)
    tag, _refresh = await service.create_smart_tag(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Invoices",
        rule=DocumentRule(document_types=("invoice",)),
    )
    document.document_type = "generic_pdf"
    await session.commit()

    changed = await service.synchronize_document(
        owner_id=owner.id,
        document_id=document.id,
        actor_id=owner.id,
    )
    link = await session.get(
        DocumentTag,
        {"document_id": document.id, "tag_id": tag.id},
    )

    assert changed == (document.id,)
    assert link is None


async def test_smart_tags_exclude_archived_documents_by_default(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, "archived-smart-tag@example.test")
    document = await create_document(
        session,
        owner_id=owner.id,
        title="Archived invoice",
        document_type="invoice",
    )
    document.status = DocumentStatus.ARCHIVED.value
    await session.commit()
    service = TagService(session)

    tag, refresh = await service.create_smart_tag(
        owner_id=owner.id,
        actor_id=owner.id,
        name="Current invoices",
        rule=DocumentRule(document_types=("invoice",)),
    )
    link = await session.get(
        DocumentTag,
        {"document_id": document.id, "tag_id": tag.id},
    )

    assert refresh.evaluated == 1
    assert refresh.matched == 0
    assert refresh.evaluated_at is not None
    assert link is None

    with pytest.raises(InvalidSmartTagRuleError):
        await service.create_smart_tag(
            owner_id=owner.id,
            actor_id=owner.id,
            name="Archived invoices",
            rule=DocumentRule(
                document_types=("invoice",),
                include_archived=True,
            ),
        )


async def create_user(session: AsyncSession, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.flush()
    return user


async def create_document(
    session: AsyncSession,
    *,
    owner_id: UUID,
    title: str,
    document_type: str = "generic_pdf",
    organization: str | None = None,
    issuer: str | None = None,
    document_date: date | None = None,
) -> Document:
    identifier = uuid4()
    document = Document(
        owner_id=owner_id,
        title=title,
        original_filename=f"{identifier}.pdf",
        content_type="application/pdf",
        file_size_bytes=128,
        sha256_hash=identifier.hex * 2,
        storage_bucket="documents",
        storage_key=f"{identifier}.pdf",
        status=DocumentStatus.READY.value,
        document_type=document_type,
        organization=organization,
        issuer=issuer,
        document_date=document_date,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document
