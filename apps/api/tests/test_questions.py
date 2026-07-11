from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.chunking import chunk_page_text
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.ai import HashingEmbeddingProvider
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextChunk,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.identity.infrastructure.models import User
from papervault_api.questions.application.service import (
    LocalExtractiveAnswerProvider,
    QuestionAnsweringService,
    question_concepts,
)

PAYSLIP_TEXT = """
WORKHALL PRIVATE LIMITED
Period Beginning 1-Aug-22
Period Ending 31-Aug-22
TOTAL EARNINGS INR 31,000.00
TOTAL DEDUCTIONS INR 2,825.00
NET PAY INR 28,175.00
"""


def test_chunk_page_text_preserves_page_and_overlap() -> None:
    chunks = chunk_page_text(
        3,
        " ".join(f"word-{index}" for index in range(12)),
        chunk_words=5,
        overlap_words=2,
    )

    assert [chunk.page_number for chunk in chunks] == [3, 3, 3, 3]
    assert chunks[0].content_text == "word-0 word-1 word-2 word-3 word-4"
    assert chunks[1].content_text.startswith("word-3 word-4")


def test_question_concepts_normalize_inflections_and_this_year() -> None:
    concepts = question_concepts("Show warranty documents expiring this year")

    assert any("warranty" in concept for concept in concepts)
    assert any("expiry" in concept for concept in concepts)
    assert any(str(datetime.now(UTC).year) in concept for concept in concepts)


async def test_question_answering_returns_page_citations_and_refuses_unknowns(
    session: AsyncSession,
) -> None:
    user = User(email="questions@example.com")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="August 2022 Payslip",
        original_filename="08-2022-Aug.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash="9" * 64,
        storage_bucket="documents",
        storage_key="questions/payslip.pdf",
        status=DocumentStatus.READY.value,
        document_type="salary_slip",
    )
    session.add(document)
    await session.flush()
    extraction = DocumentTextExtraction(
        document_id=document.id,
        source=TextExtractionSource.EMBEDDED_TEXT.value,
        status=TextExtractionStatus.SUCCEEDED.value,
        content_text=PAYSLIP_TEXT,
        page_count=1,
        is_current=True,
    )
    session.add(extraction)
    await session.flush()
    session.add(
        DocumentTextPage(
            text_extraction_id=extraction.id,
            page_number=1,
            content_text=PAYSLIP_TEXT,
        )
    )
    await session.commit()

    service = QuestionAnsweringService(
        session=session,
        embedding_provider=HashingEmbeddingProvider(16),
        answer_provider=LocalExtractiveAnswerProvider(),
    )

    answer = await service.ask(
        owner_id=user.id,
        question="What was my salary in August 2022?",
    )
    refusal = await service.ask(
        owner_id=user.id,
        question="What is the registration number of my spacecraft?",
    )

    chunks = (
        await session.execute(
            select(DocumentTextChunk).where(DocumentTextChunk.document_id == document.id)
        )
    ).scalars()
    assert chunks.one().page_number == 1
    assert answer.answered is True
    assert answer.confidence_score >= 0.7
    assert answer.citations[0].document_id == document.id
    assert answer.citations[0].page_number == 1
    assert "28,175" in answer.answer
    assert refusal.answered is False
    assert refusal.citations == ()
