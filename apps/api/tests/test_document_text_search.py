from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.text_search import (
    DocumentTextSearchService,
    find_text_matches,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.identity.infrastructure.models import User


def test_find_text_matches_returns_bounded_page_aware_excerpts() -> None:
    matches, total = find_text_matches(
        (
            (1, "January salary was 1000. February salary was 1100."),
            (2, "March salary was 1200."),
        ),
        query="salary",
        limit=2,
        context_characters=12,
    )

    assert total == 3
    assert len(matches) == 2
    assert matches[0].page_number == 1
    assert matches[0].match == "salary"
    assert matches[0].before == "January"
    assert matches[0].after == "was 1000. F..."


async def test_document_text_search_uses_current_extraction_pages(
    session: AsyncSession,
) -> None:
    user = User(email="search-reader@example.com")
    other_user = User(email="other-reader@example.com")
    session.add_all((user, other_user))
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Salary statement",
        original_filename="salary.pdf",
        content_type="application/pdf",
        file_size_bytes=32,
        sha256_hash="f" * 64,
        storage_bucket="documents",
        storage_key=f"{uuid4()}/salary.pdf",
        document_type="salary_slip",
    )
    session.add(document)
    await session.flush()
    extraction = DocumentTextExtraction(
        document_id=document.id,
        source="embedded_text",
        status="succeeded",
        content_text="January salary\n\nFebruary salary",
        page_count=2,
        is_current=True,
    )
    session.add(extraction)
    await session.flush()
    session.add_all(
        (
            DocumentTextPage(
                text_extraction_id=extraction.id,
                page_number=1,
                content_text="January salary",
            ),
            DocumentTextPage(
                text_extraction_id=extraction.id,
                page_number=2,
                content_text="February salary",
            ),
        )
    )
    await session.commit()

    result = await DocumentTextSearchService(session).search(
        owner_id=user.id,
        document_id=document.id,
        query="salary",
        limit=10,
    )
    forbidden = await DocumentTextSearchService(session).search(
        owner_id=other_user.id,
        document_id=document.id,
        query="salary",
        limit=10,
    )

    assert result is not None
    assert result.total_matches == 2
    assert result.page_mapping_available is True
    assert [match.page_number for match in result.matches] == [1, 2]
    assert forbidden is None
