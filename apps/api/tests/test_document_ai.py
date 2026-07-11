from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.ai import DocumentAIProcessingService
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.ai import (
    HashingEmbeddingProvider,
    LocalDocumentAIProvider,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentEmbedding,
    DocumentMetadataRecord,
    DocumentTextExtraction,
)
from papervault_api.identity.infrastructure.models import User
from papervault_api.tags.infrastructure.models import DocumentTag, Tag

SALARY_TEXT = """
Salary Slip
Employer: Acme Technologies
Month: 1
Year: 2025
Gross Salary: INR 150,000
Net Salary: INR 120,000
Employee earnings and deductions are listed below.
"""


def test_local_ai_provider_classifies_and_extracts_salary_metadata() -> None:
    provider = LocalDocumentAIProvider()

    result = provider.analyze(SALARY_TEXT, "generic_pdf")

    assert result.category == "salary_slip"
    assert result.confidence_score >= 0.55
    assert result.extracted_metadata["employer"] == "Acme Technologies"
    assert result.extracted_metadata["net_salary"] == 120000.0
    assert "salary-slip" in result.suggested_tags


def test_hashing_embedding_provider_is_deterministic() -> None:
    provider = HashingEmbeddingProvider(dimensions=16)

    first = provider.embed("salary slip net salary")
    second = provider.embed("salary slip net salary")

    assert first.vector == second.vector
    assert first.dimensions == 16
    assert len(first.vector) == 16
    assert first.vector_norm > 0


async def test_ai_processing_service_persists_analysis_embedding_and_metadata(
    session: AsyncSession,
) -> None:
    user = User(email="ai@example.com")
    session.add(user)
    await session.flush()

    document = Document(
        owner_id=user.id,
        title="Salary Slip",
        original_filename="salary.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        sha256_hash="c" * 64,
        storage_bucket="documents",
        storage_key="salary.pdf",
        status=DocumentStatus.READY.value,
        document_type="generic_pdf",
    )
    session.add(document)
    await session.flush()
    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            source=TextExtractionSource.EMBEDDED_TEXT.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text=SALARY_TEXT,
            page_count=1,
            extractor="test",
            is_current=True,
        ),
    )
    await session.commit()

    service = DocumentAIProcessingService(
        session=session,
        ai_provider=LocalDocumentAIProvider(),
        embedding_provider=HashingEmbeddingProvider(dimensions=16),
        classification_threshold=0.55,
    )

    await service.process_document(document.id)

    refreshed_document = await session.get(Document, document.id)
    analyses = (
        await session.execute(
            select(DocumentAIAnalysis).where(DocumentAIAnalysis.document_id == document.id),
        )
    ).scalars()
    embeddings = (
        await session.execute(
            select(DocumentEmbedding).where(DocumentEmbedding.document_id == document.id),
        )
    ).scalars()
    metadata_records = (
        await session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document.id,
            ),
        )
    ).scalars()

    analysis = analyses.one()
    embedding = embeddings.one()
    metadata = metadata_records.one()
    automatic_tags = (
        await session.execute(
            select(Tag)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document.id),
        )
    ).scalars()

    assert refreshed_document is not None
    assert refreshed_document.document_type == "salary_slip"
    assert refreshed_document.summary is not None
    assert analysis.category == "salary_slip"
    assert analysis.keywords
    assert analysis.extracted_metadata["gross_salary"] == 150000.0
    assert embedding.dimensions == 16
    assert len(embedding.vector) == 16
    assert metadata.schema_name == "salary_slip"
    assert metadata.data["net_salary"] == 120000.0
    assert "salary-slip" in {tag.slug for tag in automatic_tags}
