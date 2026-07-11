import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.duplicates import (
    CONTENT_SIMILARITY_METHOD,
    EXACT_TEXT_METHOD,
    OCR_SIMILARITY_METHOD,
    DuplicateDetectionService,
    build_text_fingerprint,
)
from papervault_api.documents.application.lifecycle import (
    DocumentLifecycleService,
    DuplicateMergeCommand,
    InvalidDuplicateMergeError,
)
from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentDuplicateFingerprint,
    DocumentTextExtraction,
)
from papervault_api.identity.infrastructure.models import User


def test_text_fingerprints_are_deterministic_and_normalize_formatting() -> None:
    first = build_text_fingerprint(
        "Invoice 100\nVendor: Example Company\n" + "item amount tax total " * 8,
        min_tokens=12,
    )
    second = build_text_fingerprint(
        "INVOICE 100 vendor example company " + "item amount tax total " * 8,
        min_tokens=12,
    )

    assert first is not None
    assert second is not None
    assert first.normalized_text_sha256 == second.normalized_text_sha256
    assert first.minhash_signature == second.minhash_signature
    assert len(first.bucket_hashes) == 8


async def test_duplicate_candidates_include_exact_content_and_ocr_similarity(
    session: AsyncSession,
) -> None:
    user = User(email="duplicates@example.com")
    session.add(user)
    await session.flush()
    base_text = _document_text()
    exact_text_first = await _add_document(
        session,
        user=user,
        title="Invoice Original",
        text=base_text,
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    exact_text_second = await _add_document(
        session,
        user=user,
        title="Invoice Export",
        text=base_text.upper(),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    content_first = await _add_document(
        session,
        user=user,
        title="Policy Original",
        text=_document_text(prefix="policy coverage premium renewal"),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    content_second = await _add_document(
        session,
        user=user,
        title="Policy Revised Scan",
        text=_document_text(
            prefix="policy coverage premium renewal",
            replacement="corrected",
        ),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    ocr_first = await _add_document(
        session,
        user=user,
        title="Receipt Original",
        text=_document_text(prefix="receipt vendor purchase total"),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    ocr_second = await _add_document(
        session,
        user=user,
        title="Receipt OCR Copy",
        text=_document_text(
            prefix="receipt vendor purchase total",
            replacement="recognised",
        ),
        source=TextExtractionSource.OCR,
    )
    await session.commit()

    service = DuplicateDetectionService(
        session,
        content_similarity_threshold=0.7,
        ocr_similarity_threshold=0.65,
        min_tokens=12,
    )
    refresh = await service.refresh_owner(user.id)
    candidates = await service.list_candidates(user.id)

    assert refresh.updated == 6
    assert {
        fingerprint.document_id
        for fingerprint in (await session.execute(select(DocumentDuplicateFingerprint))).scalars()
    } == {
        exact_text_first.id,
        exact_text_second.id,
        content_first.id,
        content_second.id,
        ocr_first.id,
        ocr_second.id,
    }
    methods_by_titles = {
        frozenset(document.title for document in candidate.documents): candidate.method
        for candidate in candidates
    }
    assert methods_by_titles[frozenset({"Invoice Original", "Invoice Export"})] == EXACT_TEXT_METHOD
    assert (
        methods_by_titles[frozenset({"Policy Original", "Policy Revised Scan"})]
        == CONTENT_SIMILARITY_METHOD
    )
    assert (
        methods_by_titles[frozenset({"Receipt Original", "Receipt OCR Copy"})]
        == OCR_SIMILARITY_METHOD
    )


async def test_non_exact_merge_requires_confirmation_and_revalidates_fingerprints(
    session: AsyncSession,
) -> None:
    user = User(email="duplicate-merge@example.com")
    session.add(user)
    await session.flush()
    kept = await _add_document(
        session,
        user=user,
        title="Statement Original",
        text=_document_text(),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    duplicate = await _add_document(
        session,
        user=user,
        title="Statement Export",
        text=_document_text().upper(),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    await session.commit()
    detector = DuplicateDetectionService(session, min_tokens=12)
    await detector.refresh_owner(user.id)
    lifecycle = DocumentLifecycleService(session, duplicate_similarity_min_tokens=12)

    with pytest.raises(
        InvalidDuplicateMergeError,
        match="require explicit confirmation",
    ):
        await lifecycle.merge_duplicates(
            DuplicateMergeCommand(
                owner_id=user.id,
                actor_id=user.id,
                keep_document_id=kept.id,
                duplicate_document_ids=(duplicate.id,),
                match_method=EXACT_TEXT_METHOD,
            )
        )

    result = await lifecycle.merge_duplicates(
        DuplicateMergeCommand(
            owner_id=user.id,
            actor_id=user.id,
            keep_document_id=kept.id,
            duplicate_document_ids=(duplicate.id,),
            match_method=EXACT_TEXT_METHOD,
            confirm_non_exact=True,
        )
    )

    assert result is not None
    assert result.kept_document.status == DocumentStatus.READY.value
    assert result.archived_documents[0].status == DocumentStatus.ARCHIVED.value


async def test_non_exact_merge_rejects_a_stale_extraction_fingerprint(
    session: AsyncSession,
) -> None:
    user = User(email="stale-duplicate@example.com")
    session.add(user)
    await session.flush()
    kept = await _add_document(
        session,
        user=user,
        title="Contract Original",
        text=_document_text(prefix="contract party term renewal"),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    duplicate = await _add_document(
        session,
        user=user,
        title="Contract Export",
        text=_document_text(prefix="contract party term renewal").upper(),
        source=TextExtractionSource.EMBEDDED_TEXT,
    )
    await session.commit()
    await DuplicateDetectionService(session, min_tokens=12).refresh_owner(user.id)

    current_extraction = await session.scalar(
        select(DocumentTextExtraction).where(
            DocumentTextExtraction.document_id == duplicate.id,
            DocumentTextExtraction.is_current.is_(True),
        )
    )
    assert current_extraction is not None
    current_extraction.is_current = False
    session.add(
        DocumentTextExtraction(
            document_id=duplicate.id,
            source=TextExtractionSource.EMBEDDED_TEXT.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text=_document_text(prefix="unrelated certificate education award"),
            page_count=1,
            extractor="test",
            is_current=True,
        )
    )
    await session.commit()

    with pytest.raises(
        InvalidDuplicateMergeError,
        match="no longer meet",
    ):
        await DocumentLifecycleService(
            session,
            duplicate_similarity_min_tokens=12,
        ).merge_duplicates(
            DuplicateMergeCommand(
                owner_id=user.id,
                actor_id=user.id,
                keep_document_id=kept.id,
                duplicate_document_ids=(duplicate.id,),
                match_method=EXACT_TEXT_METHOD,
                confirm_non_exact=True,
            )
        )


async def _add_document(
    session: AsyncSession,
    *,
    user: User,
    title: str,
    text: str,
    source: TextExtractionSource,
) -> Document:
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
    document = Document(
        owner_id=user.id,
        title=title,
        original_filename=f"{title.casefold().replace(' ', '-')}.pdf",
        content_type="application/pdf",
        file_size_bytes=len(text.encode("utf-8")),
        sha256_hash=digest,
        storage_bucket="documents",
        storage_key=f"duplicates/{digest}.pdf",
        status=DocumentStatus.READY.value,
        document_type="generic_pdf",
    )
    session.add(document)
    await session.flush()
    session.add(
        DocumentTextExtraction(
            document_id=document.id,
            source=source.value,
            status=TextExtractionStatus.SUCCEEDED.value,
            content_text=text,
            page_count=1,
            extractor="test",
            is_current=True,
        )
    )
    return document


def _document_text(
    *,
    prefix: str = "invoice vendor purchase amount",
    replacement: str = "original",
) -> str:
    marker = prefix.split()[0]
    body = " ".join(f"{marker} line {index} description quantity value" for index in range(40))
    return f"{prefix} {replacement} {body} final total and payment terms"
