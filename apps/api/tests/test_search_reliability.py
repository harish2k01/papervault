from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.ai import EmbeddingResult
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.identity.infrastructure.models import User
from papervault_api.search.application import service as search_module
from papervault_api.search.application.service import (
    DocumentSearchService,
    SearchRequest,
    build_highlights,
    score_keyword,
)
from papervault_api.search.domain.enums import SearchMode


class UnavailableEmbeddingProvider:
    def embed(self, text: str) -> EmbeddingResult:
        raise ConnectionError("Embedding service unavailable")


@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("672839", "Receipt reference 672839"),
        ("12", "Document number 12"),
        ("Li", "Statement issued to Li"),
        ("東京", "東京 receipt"),
    ],
)
def test_keyword_search_and_excerpts_preserve_numbers_short_names_and_unicode(
    query: str, text: str
) -> None:
    assert score_keyword(query, text) == 1
    assert query.lower() in build_highlights(query, text)[0].lower()


async def test_search_finds_numeric_reference_in_extracted_text(session: AsyncSession) -> None:
    owner_id, document_id = await add_searchable_document(session)
    results = await DocumentSearchService(
        session=session, embedding_provider_name="local", embedding_dimensions=16
    ).search(SearchRequest(owner_id=owner_id, query="672839", mode=SearchMode.KEYWORD))
    assert [result.document_id for result in results] == [document_id]
    assert "672839" in results[0].highlights[0]


async def add_searchable_document(session: AsyncSession) -> tuple[UUID, UUID]:
    user = User(email="reliable-search@example.com")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Saved document",
        original_filename="scan.pdf",
        content_type="application/pdf",
        file_size_bytes=32,
        sha256_hash="a" * 64,
        storage_bucket="documents",
        storage_key="original.pdf",
        status="ready",
        created_at=datetime.now(UTC) - timedelta(days=365),
    )
    session.add(document)
    await session.flush()
    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            source="embedded_text",
            status="succeeded",
            content_text="Replacement compressor reference ZXQ918273. Receipt number 672839.",
            is_current=True,
        )
    )
    await session.commit()
    return user.id, document.id


async def test_fallback_search_finds_content_older_than_latest_500_documents(
    session: AsyncSession,
) -> None:
    owner_id, document_id = await add_searchable_document(session)
    session.add_all(
        Document(
            owner_id=owner_id,
            title=f"Recent document {index}",
            original_filename=f"recent-{index}.pdf",
            content_type="application/pdf",
            file_size_bytes=1,
            sha256_hash=f"{index:064x}",
            storage_bucket="documents",
            storage_key=f"recent-{index}.pdf",
            status="ready",
        )
        for index in range(501)
    )
    await session.commit()
    service = DocumentSearchService(
        session=session, embedding_provider_name="local", embedding_dimensions=16
    )
    results = await service.search(
        SearchRequest(owner_id=owner_id, query="ZXQ918273", mode=SearchMode.KEYWORD)
    )
    assert [result.document_id for result in results] == [document_id]
    assert "ZXQ918273" in results[0].highlights[0]

    first_page = await service.search(
        SearchRequest(owner_id=owner_id, mode=SearchMode.KEYWORD, limit=100)
    )
    last_page = await service.search(
        SearchRequest(owner_id=owner_id, mode=SearchMode.KEYWORD, limit=100, offset=500)
    )
    assert len(first_page) == 100
    assert len(last_page) == 2
    assert document_id in {result.document_id for result in last_page}
    assert not {r.document_id for r in first_page} & {r.document_id for r in last_page}


async def test_hybrid_search_keeps_working_when_embedding_provider_is_down(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id, document_id = await add_searchable_document(session)
    monkeypatch.setattr(
        search_module, "build_embedding_provider", lambda *args: UnavailableEmbeddingProvider()
    )
    service = DocumentSearchService(
        session=session, embedding_provider_name="ollama", embedding_dimensions=16
    )
    results = await service.search(SearchRequest(owner_id=owner_id, query="ZXQ918273"))
    assert [result.document_id for result in results] == [document_id]
    assert (await service.list_recent_searches(owner_id))[0].mode == "keyword"


@pytest.mark.parametrize(
    ("mode", "fallback"), [(SearchMode.SEMANTIC, True), (SearchMode.HYBRID, False)]
)
async def test_explicit_semantic_or_disabled_fallback_does_not_silently_change_mode(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    mode: SearchMode,
    fallback: bool,
) -> None:
    owner_id, _ = await add_searchable_document(session)
    monkeypatch.setattr(
        search_module, "build_embedding_provider", lambda *args: UnavailableEmbeddingProvider()
    )
    service = DocumentSearchService(
        session=session,
        embedding_provider_name="ollama",
        embedding_dimensions=16,
        query_fallback_enabled=fallback,
    )
    with pytest.raises(ConnectionError):
        await service.search(SearchRequest(owner_id=owner_id, query="ZXQ918273", mode=mode))


async def test_keyword_search_never_calls_embedding_provider(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id, document_id = await add_searchable_document(session)

    def unexpected_provider(*args: object) -> None:
        raise AssertionError("Keyword search must not require a model")

    monkeypatch.setattr(search_module, "build_embedding_provider", unexpected_provider)
    service = DocumentSearchService(
        session=session, embedding_provider_name="ollama", embedding_dimensions=16
    )
    results = await service.search(
        SearchRequest(owner_id=owner_id, query="ZXQ918273", mode=SearchMode.KEYWORD)
    )
    other_results = await service.search(
        SearchRequest(owner_id=UUID(int=7), query="ZXQ918273", mode=SearchMode.KEYWORD)
    )
    assert [result.document_id for result in results] == [document_id]
    assert other_results == ()
