from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.domain.enums import (
    AIAnalysisStatus,
    DocumentStatus,
    MetadataSource,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextExtraction,
)
from papervault_api.identity.infrastructure.models import User
from papervault_api.search.application.indexing import SearchIndexDocument, SearchIndexingService
from papervault_api.search.infrastructure.opensearch import (
    OpenSearchDocumentIndex,
    OpenSearchResponse,
    document_to_opensearch_body,
)
from papervault_api.tags.infrastructure.models import DocumentTag, Tag


class FakeSearchDocumentIndex:
    def __init__(self) -> None:
        self.ensure_calls = 0
        self.indexed_documents: list[SearchIndexDocument] = []
        self.deleted_documents: list[UUID] = []

    def ensure_index(self) -> None:
        self.ensure_calls += 1

    def index_document(self, document: SearchIndexDocument) -> None:
        self.indexed_documents.append(document)

    def delete_document(self, document_id: UUID) -> None:
        self.deleted_documents.append(document_id)


class FakeOpenSearchClient:
    def __init__(self, *, exists: bool) -> None:
        self.exists_response = exists
        self.requests: list[tuple[str, str, dict[str, Any] | None, bool]] = []

    def exists(self, path: str) -> bool:
        self.requests.append(("HEAD", path, None, False))
        return self.exists_response

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        ignore_not_found: bool = False,
    ) -> OpenSearchResponse:
        self.requests.append((method, path, body, ignore_not_found))
        return OpenSearchResponse(status_code=200, body={"acknowledged": True})


async def test_search_indexing_service_projects_document_state(
    session: AsyncSession,
) -> None:
    user = User(email="index@example.com")
    session.add(user)
    await session.flush()

    document = Document(
        owner_id=user.id,
        title="Warranty Invoice",
        original_filename="warranty-invoice.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash="f" * 64,
        storage_bucket="documents",
        storage_key="warranty-invoice.pdf",
        status=DocumentStatus.READY.value,
        document_type="invoice",
        issuer="Acme Store",
        organization="Acme",
        summary="Invoice with warranty details",
    )
    session.add(document)
    await session.flush()

    session.add_all(
        [
            DocumentTextExtraction(
                document_id=document.id,
                source=TextExtractionSource.OCR.value,
                status=TextExtractionStatus.SUCCEEDED.value,
                content_text="Purchased tablet with two year warranty",
                is_current=True,
            ),
            DocumentEmbedding(
                document_id=document.id,
                provider="local",
                model="hashing-embedding",
                dimensions=3,
                vector=[0.1, 0.2, 0.3],
                vector_norm=0.374,
                source_text_sha256="a" * 64,
                is_current=True,
            ),
            DocumentAIAnalysis(
                document_id=document.id,
                provider="local",
                model="rules-v1",
                status=AIAnalysisStatus.SUCCEEDED.value,
                summary="Invoice summary",
                keywords=["invoice", "warranty"],
                entities=[{"kind": "vendor", "value": "Acme Store"}],
                suggested_tags=["warranty"],
                category="invoice",
                confidence_score=0.9,
                extracted_metadata={"vendor": "Acme Store"},
                is_current=True,
            ),
            DocumentMetadataRecord(
                document_id=document.id,
                schema_name="invoice",
                data={"vendor": "Acme Store", "total_amount": 1000},
                source=MetadataSource.AI.value,
                is_current=True,
            ),
        ],
    )
    tag = Tag(owner_id=user.id, name="Warranty", slug="warranty")
    session.add(tag)
    await session.flush()
    session.add(DocumentTag(document_id=document.id, tag_id=tag.id, assigned_by_id=user.id))
    await session.commit()
    await session.refresh(document)

    fake_index = FakeSearchDocumentIndex()
    service = SearchIndexingService(session=session, search_index=fake_index)

    indexed = await service.index_document(document.id)

    projection = fake_index.indexed_documents[0]
    assert indexed is True
    assert fake_index.ensure_calls == 1
    assert projection.document_id == document.id
    assert projection.owner_id == user.id
    assert projection.text == "Purchased tablet with two year warranty"
    assert projection.tags == ("warranty",)
    assert projection.metadata["total_amount"] == 1000
    assert projection.keywords == ("invoice", "warranty")
    assert projection.embedding == (0.1, 0.2, 0.3)
    assert projection.source_text_sha256 == "a" * 64


async def test_search_indexing_service_deletes_missing_document(session: AsyncSession) -> None:
    fake_index = FakeSearchDocumentIndex()
    service = SearchIndexingService(session=session, search_index=fake_index)
    missing_document_id = uuid4()

    indexed = await service.index_document(missing_document_id)

    assert indexed is False
    assert fake_index.deleted_documents == [missing_document_id]


async def test_search_indexing_service_rebuilds_owner_documents(
    session: AsyncSession,
) -> None:
    user = User(email="rebuild@example.com")
    other_user = User(email="other@example.com")
    session.add_all([user, other_user])
    await session.flush()
    for owner, title in ((user, "First"), (user, "Second"), (other_user, "Other")):
        session.add(
            Document(
                owner_id=owner.id,
                title=title,
                original_filename=f"{title.lower()}.pdf",
                content_type="application/pdf",
                file_size_bytes=100,
                sha256_hash=(title.lower()[0] * 64),
                storage_bucket="documents",
                storage_key=f"{title.lower()}.pdf",
                status=DocumentStatus.READY.value,
                document_type="generic_pdf",
            ),
        )
    await session.commit()

    fake_index = FakeSearchDocumentIndex()
    service = SearchIndexingService(session=session, search_index=fake_index)

    indexed_count = await service.index_owner_documents(user.id, limit=500)

    assert indexed_count == 2
    assert fake_index.ensure_calls == 1
    assert {document.title for document in fake_index.indexed_documents} == {"First", "Second"}


def test_opensearch_document_index_creates_index_and_upserts_document() -> None:
    client = FakeOpenSearchClient(exists=False)
    index = OpenSearchDocumentIndex(
        client=client,  # type: ignore[arg-type]
        index_name="papervault-documents-v1",
        embedding_dimensions=3,
    )
    document = SearchIndexDocument(
        document_id=uuid4(),
        owner_id=uuid4(),
        title="Passport",
        original_filename="passport.pdf",
        content_type="application/pdf",
        status="ready",
        document_type="passport",
        summary="Passport scan",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
        updated_at=datetime(2026, 7, 8, tzinfo=UTC),
        text="passport expiry date",
        tags=("identity",),
        embedding=(0.1, 0.2, 0.3),
        embedding_dimensions=3,
    )

    index.ensure_index()
    index.index_document(document)

    create_request = client.requests[1]
    upsert_request = client.requests[2]
    assert create_request[0] == "PUT"
    assert create_request[1] == "papervault-documents-v1"
    assert create_request[2]["mappings"]["properties"]["embedding"]["dimension"] == 3
    assert upsert_request[0] == "PUT"
    assert upsert_request[1].endswith(f"/_doc/{document.document_id}")
    assert upsert_request[2]["owner_id"] == str(document.owner_id)
    assert upsert_request[2]["tags"] == ["identity"]
    assert upsert_request[2]["embedding"] == [0.1, 0.2, 0.3]


def test_opensearch_document_index_delete_ignores_missing_document() -> None:
    client = FakeOpenSearchClient(exists=True)
    index = OpenSearchDocumentIndex(
        client=client,  # type: ignore[arg-type]
        index_name="papervault-documents-v1",
        embedding_dimensions=3,
    )
    document_id = uuid4()

    index.delete_document(document_id)

    assert client.requests == [
        ("DELETE", f"papervault-documents-v1/_doc/{document_id}", None, True),
    ]


def test_document_to_opensearch_body_omits_empty_optional_fields() -> None:
    document = SearchIndexDocument(
        document_id=uuid4(),
        owner_id=uuid4(),
        title="Receipt",
        original_filename="receipt.png",
        content_type="image/png",
        status="ready",
        document_type="receipt",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
        updated_at=datetime(2026, 7, 8, tzinfo=UTC),
    )

    body = document_to_opensearch_body(document)

    assert "summary" not in body
    assert "embedding" not in body
    assert body["tags"] == []
