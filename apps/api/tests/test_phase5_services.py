from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.lifecycle import (
    DocumentLifecycleService,
    DocumentUpdateCommand,
    MetadataUpdateCommand,
)
from papervault_api.documents.application.read import DocumentReadService
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    MetadataSource,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.ai import HashingEmbeddingProvider
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextExtraction,
)
from papervault_api.identity.infrastructure.models import User
from papervault_api.notifications.application.service import NotificationService
from papervault_api.notifications.domain.enums import NotificationStatus
from papervault_api.search.application.service import (
    DocumentSearchService,
    SearchFilters,
    SearchRequest,
    SearchResult,
)
from papervault_api.search.domain.enums import SearchMode
from papervault_api.tags.application.service import TagService
from papervault_api.timeline.infrastructure.models import TimelineEvent


class FakeSearchQueryIndex:
    def __init__(self, results: tuple[SearchResult, ...]) -> None:
        self.results = results
        self.requests: list[SearchRequest] = []
        self.query_embeddings: list[tuple[float, ...] | None] = []

    def search(
        self,
        request: SearchRequest,
        query_embedding: tuple[float, ...] | None,
    ) -> tuple[SearchResult, ...]:
        self.requests.append(request)
        self.query_embeddings.append(query_embedding)
        return self.results


class FailingSearchQueryIndex:
    def search(
        self,
        request: SearchRequest,
        query_embedding: tuple[float, ...] | None,
    ) -> tuple[SearchResult, ...]:
        raise RuntimeError("OpenSearch unavailable")


async def test_search_service_keyword_semantic_recent_and_saved(session: AsyncSession) -> None:
    user, document = await create_document_with_text(
        session,
        title="Credit Card May Statement",
        text="Credit card statement with total due INR 10000 and payment due date 2026-08-01",
        document_type="credit_card_statement",
    )
    await create_document_with_text(
        session,
        title="Passport Copy",
        text="Passport document with nationality and date of expiry.",
        document_type="passport",
    )

    service = DocumentSearchService(
        session=session,
        embedding_provider_name="local",
        embedding_dimensions=16,
    )

    results = await service.search(
        SearchRequest(
            owner_id=user.id,
            query="credit card due",
            mode=SearchMode.HYBRID,
            filters=SearchFilters(),
        ),
    )
    saved = await service.save_search(
        owner_id=user.id,
        name="Credit cards",
        query="credit card",
        mode=SearchMode.KEYWORD,
        filters=SearchFilters(document_type="credit_card_statement"),
    )
    recent = await service.list_recent_searches(user.id)

    assert results[0].document_id == document.id
    assert results[0].score > 0
    assert saved.name == "Credit cards"
    assert recent[0].query == "credit card due"


async def test_search_service_uses_query_index_and_records_recent(
    session: AsyncSession,
) -> None:
    user, document = await create_document_with_text(
        session,
        title="Salary Slip January",
        text="Salary slip with net salary INR 120000",
        document_type="salary_slip",
    )
    indexed_result = SearchResult(
        document_id=document.id,
        title=document.title,
        original_filename=document.original_filename,
        document_type=document.document_type,
        status=document.status,
        summary=document.summary,
        created_at=document.created_at,
        score=12.5,
        highlights=("net salary INR 120000",),
    )
    fake_index = FakeSearchQueryIndex((indexed_result,))
    service = DocumentSearchService(
        session=session,
        embedding_provider_name="local",
        embedding_dimensions=16,
        search_query_index=fake_index,
    )

    results = await service.search(
        SearchRequest(
            owner_id=user.id,
            query="salary january",
            mode=SearchMode.HYBRID,
        ),
    )
    recent = await service.list_recent_searches(user.id)

    assert results == (indexed_result,)
    assert fake_index.requests[0].owner_id == user.id
    assert fake_index.query_embeddings[0] is not None
    assert recent[0].query == "salary january"


async def test_search_service_falls_back_to_database_when_query_index_fails(
    session: AsyncSession,
) -> None:
    user, document = await create_document_with_text(
        session,
        title="Insurance Policy",
        text="Insurance policy with expiry date",
        document_type="insurance_policy",
    )
    service = DocumentSearchService(
        session=session,
        embedding_provider_name="local",
        embedding_dimensions=16,
        search_query_index=FailingSearchQueryIndex(),
        query_fallback_enabled=True,
    )

    results = await service.search(
        SearchRequest(
            owner_id=user.id,
            query="insurance expiry",
            mode=SearchMode.HYBRID,
        ),
    )

    assert results[0].document_id == document.id
    assert results[0].score > 0


async def test_tag_service_attaches_tag_and_writes_timeline(session: AsyncSession) -> None:
    user, document = await create_document_with_text(
        session, title="Warranty", text="Warranty expires"
    )
    tag_service = TagService(session)
    tag = await tag_service.create_tag(owner_id=user.id, name="Warranty")

    attached = await tag_service.attach_tag(
        owner_id=user.id, document_id=document.id, tag_id=tag.id
    )

    timeline_events = (
        await session.execute(
            select(TimelineEvent).where(TimelineEvent.document_id == document.id),
        )
    ).scalars()

    assert attached is True
    assert tag.slug == "warranty"
    assert any(event.event_type == "tags_changed" for event in timeline_events)


async def test_duplicate_candidates_group_by_sha256(session: AsyncSession) -> None:
    user, first = await create_document_with_text(session, title="Invoice 1", text="Invoice")
    duplicate = Document(
        owner_id=user.id,
        title="Invoice 1 Copy",
        original_filename="invoice-copy.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash=first.sha256_hash,
        storage_bucket="documents",
        storage_key="invoice-copy.pdf",
        status=DocumentStatus.READY.value,
        document_type="invoice",
    )
    session.add(duplicate)
    await session.commit()

    groups = await DocumentReadService(session).get_duplicate_candidates(user.id)

    assert len(groups) == 1
    assert {document.title for document in groups[0]} == {"Invoice 1", "Invoice 1 Copy"}


async def test_document_lifecycle_updates_metadata_archives_and_writes_timeline(
    session: AsyncSession,
) -> None:
    user, document = await create_document_with_text(
        session,
        title="Invoice",
        text="Invoice from Acme",
        document_type="invoice",
    )
    service = DocumentLifecycleService(session)

    updated_document = await service.update_document(
        DocumentUpdateCommand(
            owner_id=user.id,
            actor_id=user.id,
            document_id=document.id,
            updates={"title": "Invoice 2026", "issuer": "Acme"},
        ),
    )
    metadata = await service.replace_metadata(
        MetadataUpdateCommand(
            owner_id=user.id,
            actor_id=user.id,
            document_id=document.id,
            schema_name="invoice",
            data={
                "vendor": "Acme Store",
                "purchase_date": "2026-07-01",
                "total_amount": 1200,
            },
        ),
    )
    archived = await service.archive_document(
        owner_id=user.id,
        actor_id=user.id,
        document_id=document.id,
    )

    timeline_events = tuple(
        (
            await session.execute(
                select(TimelineEvent).where(TimelineEvent.document_id == document.id),
            )
        ).scalars(),
    )
    visible_documents = await DocumentReadService(session).list_documents(owner_id=user.id)
    all_documents = await DocumentReadService(session).list_documents(
        owner_id=user.id,
        include_archived=True,
    )
    search_results = await DocumentSearchService(
        session=session,
        embedding_provider_name="local",
        embedding_dimensions=16,
    ).search(SearchRequest(owner_id=user.id, query="", record_recent=False))

    assert updated_document is not None
    assert updated_document.title == "Invoice 2026"
    assert metadata is not None
    assert metadata.source == MetadataSource.MANUAL.value
    assert archived is not None
    assert archived.status == DocumentStatus.ARCHIVED.value
    assert archived.issuer == "Acme Store"
    assert visible_documents == ()
    assert len(all_documents) == 1
    assert search_results == ()
    assert any(event.event_type == "metadata_edited" for event in timeline_events)
    assert any(event.event_type == "document_archived" for event in timeline_events)


async def test_notification_service_generates_and_updates_due_date(session: AsyncSession) -> None:
    user, document = await create_document_with_text(
        session,
        title="Insurance Policy",
        text="Insurance policy",
        document_type="insurance_policy",
    )
    session.add(
        DocumentMetadataRecord(
            document_id=document.id,
            schema_name="insurance_policy",
            data={"expiry_date": "2026-12-31"},
            source=MetadataSource.AI.value,
            is_current=True,
        ),
    )
    await session.commit()

    service = NotificationService(session)
    notifications = await service.generate_for_document(document.id)
    updated = await service.update_status(
        owner_id=user.id,
        notification_id=notifications[0].id,
        status=NotificationStatus.READ,
    )

    assert len(notifications) == 1
    assert notifications[0].due_date == date(2026, 12, 31)
    assert updated is not None
    assert updated.status == NotificationStatus.READ.value


async def create_document_with_text(
    session: AsyncSession,
    *,
    title: str,
    text: str,
    document_type: str = "generic_pdf",
) -> tuple[User, Document]:
    user = User(email=f"{title.lower().replace(' ', '.')}@example.com")
    session.add(user)
    await session.flush()

    document = Document(
        owner_id=user.id,
        title=title,
        original_filename=f"{title.lower().replace(' ', '-')}.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash=("d" * 63) + str(len(title) % 10),
        storage_bucket="documents",
        storage_key=f"{title}.pdf",
        status=DocumentStatus.READY.value,
        document_type=document_type,
    )
    session.add(document)
    await session.flush()

    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            source=TextExtractionSource.EMBEDDED_TEXT.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text=text,
            is_current=True,
        ),
    )
    embedding = HashingEmbeddingProvider(dimensions=16).embed(text)
    session.add(
        DocumentEmbedding(
            document_id=document.id,
            provider=embedding.provider,
            model=embedding.model,
            dimensions=embedding.dimensions,
            vector=list(embedding.vector),
            vector_norm=embedding.vector_norm,
            source_text_sha256="e" * 64,
            is_current=True,
        ),
    )
    await session.commit()
    await session.refresh(document)
    return user, document
