import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentTextPage,
)


@dataclass(frozen=True, slots=True)
class DocumentTextMatch:
    page_number: int | None
    before: str
    match: str
    after: str


@dataclass(frozen=True, slots=True)
class DocumentTextSearchResult:
    query: str
    total_matches: int
    matches: tuple[DocumentTextMatch, ...]
    page_mapping_available: bool


class DocumentTextSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
        query: str,
        limit: int,
    ) -> DocumentTextSearchResult | None:
        document = await self._session.scalar(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
        )
        if document is None:
            return None

        extraction = await self._session.scalar(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
            )
        )
        if extraction is None or not extraction.content_text:
            return DocumentTextSearchResult(
                query=query, total_matches=0, matches=(), page_mapping_available=False
            )

        pages = tuple(
            (
                await self._session.execute(
                    select(DocumentTextPage)
                    .where(DocumentTextPage.text_extraction_id == extraction.id)
                    .order_by(DocumentTextPage.page_number.asc())
                )
            ).scalars()
        )
        sources = (
            tuple((page.page_number, page.content_text) for page in pages)
            if pages
            else ((None, extraction.content_text),)
        )
        matches, total_matches = find_text_matches(sources, query=query, limit=limit)
        return DocumentTextSearchResult(
            query=query,
            total_matches=total_matches,
            matches=matches,
            page_mapping_available=bool(pages),
        )


def find_text_matches(
    pages: tuple[tuple[int | None, str], ...],
    *,
    query: str,
    limit: int,
    context_characters: int = 90,
) -> tuple[tuple[DocumentTextMatch, ...], int]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches: list[DocumentTextMatch] = []
    total_matches = 0

    for page_number, content_text in pages:
        for occurrence in pattern.finditer(content_text):
            total_matches += 1
            if len(matches) >= limit:
                continue
            start = max(0, occurrence.start() - context_characters)
            end = min(len(content_text), occurrence.end() + context_characters)
            matches.append(
                DocumentTextMatch(
                    page_number=page_number,
                    before=compact_excerpt(
                        content_text[start : occurrence.start()], leading=start > 0
                    ),
                    match=content_text[occurrence.start() : occurrence.end()],
                    after=compact_excerpt(
                        content_text[occurrence.end() : end], trailing=end < len(content_text)
                    ),
                )
            )

    return tuple(matches), total_matches


def compact_excerpt(text: str, *, leading: bool = False, trailing: bool = False) -> str:
    compacted = " ".join(text.split())
    if leading and compacted:
        compacted = f"...{compacted}"
    if trailing and compacted:
        compacted = f"{compacted}..."
    return compacted
