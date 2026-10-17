from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_grounded_analysis import SourceModel

from papervault_api.documents.application.ai import DocumentAIProcessingService
from papervault_api.documents.application.read import DocumentReadService
from papervault_api.documents.infrastructure.ai import (
    HashingEmbeddingProvider,
    ModelDocumentAIProvider,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentAIAnalysis,
    DocumentMetadataRecord,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.identity.infrastructure.models import User


async def test_page_evidence_is_persisted_and_reprocessing_keeps_manual_metadata(
    session: AsyncSession,
) -> None:
    user = User(email="grounding@example.test")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Salary",
        original_filename="salary.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash="e" * 64,
        storage_bucket="documents",
        storage_key="salary",
        status="ready",
        document_type="generic_pdf",
    )
    session.add(document)
    await session.flush()
    extraction = DocumentTextExtraction(
        document_id=document.id,
        source="embedded_text",
        status="succeeded",
        content_text="Employer: Example Company\nNet Salary: INR 12000",
        page_count=2,
        is_current=True,
    )
    session.add(extraction)
    await session.flush()
    session.add_all(
        [
            DocumentTextPage(
                text_extraction_id=extraction.id,
                page_number=1,
                content_text="Employer: Example Company",
            ),
            DocumentTextPage(
                text_extraction_id=extraction.id,
                page_number=2,
                content_text="Net Salary: INR 12000",
            ),
        ]
    )
    await session.commit()

    def provider() -> ModelDocumentAIProvider:
        return ModelDocumentAIProvider(
            SourceModel(
                [
                    {
                        "category": "salary_slip",
                        "confidence_score": 0.9,
                        "extracted_metadata": {"employer": "Example Company"},
                        "field_evidence": [
                            {
                                "field": "employer",
                                "page_number": 1,
                                "quote": "Employer: Example Company",
                            }
                        ],
                        "summary_points": [
                            {"page_number": 1, "quote": "Employer: Example Company"}
                        ],
                    },
                    {
                        "category": "salary_slip",
                        "confidence_score": 0.9,
                        "extracted_metadata": {"net_salary": 12000},
                        "field_evidence": [
                            {
                                "field": "net_salary",
                                "page_number": 2,
                                "quote": "Net Salary: INR 12000",
                            }
                        ],
                        "summary_points": [{"page_number": 2, "quote": "Net Salary: INR 12000"}],
                    },
                ]
            )
        )

    async def process() -> None:
        await DocumentAIProcessingService(
            session=session,
            ai_provider=provider(),
            embedding_provider=HashingEmbeddingProvider(16),
            classification_threshold=0.55,
        ).process_document(document.id)

    await process()
    detail = await DocumentReadService(session).get_detail(
        document_id=document.id, owner_id=user.id
    )
    assert (
        detail is not None
        and detail.current_ai_analysis is not None
        and detail.current_metadata is not None
    )
    assert detail.current_ai_analysis.covered_pages == [1, 2]
    assert any(
        item["field"] == "net_salary" and item["page_number"] == 2
        for item in detail.current_ai_analysis.field_evidence
    )
    assert detail.current_metadata.confidence_score is None

    class NeverAnalyze:
        def analyze(self, text: str, current_document_type: str) -> object:
            raise AssertionError("Duplicate or stale delivery must not invoke the model")

    guarded = DocumentAIProcessingService(
        session=session,
        ai_provider=NeverAnalyze(),
        embedding_provider=HashingEmbeddingProvider(16),
        classification_threshold=0.55,
    )
    assert not await guarded.process_document(document.id, expected_extraction_id=extraction.id)
    assert not await guarded.process_document(document.id, expected_extraction_id=uuid4())

    detail.current_metadata.is_current = False
    manual = DocumentMetadataRecord(
        document_id=document.id,
        schema_name="invoice",
        schema_version=1,
        data={"vendor": "Corrected Vendor", "total_amount": 123},
        source="manual",
        is_current=True,
    )
    session.add(manual)
    document.document_type = "invoice"
    await session.commit()
    await process()
    detail = await DocumentReadService(session).get_detail(
        document_id=document.id, owner_id=user.id
    )
    assert detail is not None and detail.current_metadata is not None
    assert detail.current_metadata.id == manual.id
    assert detail.current_metadata.data == {"vendor": "Corrected Vendor", "total_amount": 123}
    assert document.document_type == "invoice"
    assert "manual_metadata_preserved:metadata" in document.review_reasons
    current = (
        await session.scalars(
            select(DocumentAIAnalysis).where(
                DocumentAIAnalysis.document_id == document.id,
                DocumentAIAnalysis.is_current.is_(True),
            )
        )
    ).all()
    assert len(current) == 1


async def test_tag_refresh_keeps_human_edits_and_remembers_rejections(
    session: AsyncSession,
) -> None:
    from papervault_api.tags.application.service import TagService
    from papervault_api.tags.infrastructure.models import DocumentTag, DocumentTagSuppression

    user = User(email="tags-grounded@example.test")
    session.add(user)
    await session.flush()
    document = Document(
        owner_id=user.id,
        title="Tags",
        original_filename="tags.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        sha256_hash="f" * 64,
        storage_bucket="documents",
        storage_key="tags",
        status="ready",
        document_type="generic_pdf",
    )
    session.add(document)
    await session.commit()
    service = TagService(session)
    await service.apply_automatic_tags(
        owner_id=user.id,
        document_id=document.id,
        suggestions=("obsolete", "retained", "rejected"),
        confidence_score=0.9,
    )
    await session.commit()
    tags = {tag.slug: tag for tag in await service.list_tags(user.id)}
    await service.attach_tag(owner_id=user.id, document_id=document.id, tag_id=tags["retained"].id)
    await service.detach_tag(owner_id=user.id, document_id=document.id, tag_id=tags["rejected"].id)
    # Legacy detach history predates the suppression table; it must also be honored.
    suppression = await session.get(
        DocumentTagSuppression, {"document_id": document.id, "tag_id": tags["rejected"].id}
    )
    assert suppression is not None
    await session.delete(suppression)
    await session.commit()
    await service.apply_automatic_tags(
        owner_id=user.id,
        document_id=document.id,
        suggestions=("fresh", "rejected"),
        confidence_score=0.9,
    )
    await session.commit()
    detail = await DocumentReadService(session).get_detail(
        document_id=document.id, owner_id=user.id
    )
    assert detail is not None
    assert {tag.slug for tag in detail.tags} == {"fresh", "retained"}
    await service.attach_tag(owner_id=user.id, document_id=document.id, tag_id=tags["rejected"].id)
    await service.apply_automatic_tags(
        owner_id=user.id,
        document_id=document.id,
        suggestions=("fresh", "rejected"),
        confidence_score=0.9,
    )
    await session.commit()
    restored = await session.get(
        DocumentTag, {"document_id": document.id, "tag_id": tags["rejected"].id}
    )
    assert restored is not None and restored.source == "manual"
    assert (
        await session.get(
            DocumentTagSuppression, {"document_id": document.id, "tag_id": tags["rejected"].id}
        )
        is None
    )
