from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.api.dependencies import (
    get_document_processing_queue,
    get_document_upload_service,
    get_object_storage,
)
from papervault_api.documents.api.schemas import (
    AIAnalysisResponse,
    DocumentDetailResponse,
    DocumentResponse,
    DocumentTagResponse,
    DocumentTextMatchResponse,
    DocumentTextSearchResponse,
    DocumentTypeResponse,
    DocumentVersionResponse,
    DuplicateCandidateDocumentResponse,
    DuplicateCandidateGroupResponse,
    DuplicateSignalsResponse,
    MergeDuplicateDocumentsRequest,
    MergeDuplicateDocumentsResponse,
    MetadataFieldDefinitionResponse,
    MetadataResponse,
    OcrTextBlockResponse,
    RefreshDuplicateFingerprintsResponse,
    ReprocessDocumentResponse,
    ReviewDocumentRequest,
    TextExtractionResponse,
    TimelineEventResponse,
    UpdateDocumentRequest,
    UpdateMetadataRequest,
    UploadDocumentResponse,
    VersionChangeResponse,
    VersionComparisonResponse,
)
from papervault_api.documents.application.deletion import DocumentDeletionService
from papervault_api.documents.application.duplicates import DuplicateDetectionService
from papervault_api.documents.application.lifecycle import (
    DocumentLifecycleService,
    DocumentUpdateCommand,
    DuplicateMergeCommand,
    InvalidDuplicateMergeError,
    InvalidMetadataError,
    MetadataUpdateCommand,
    ReviewUpdateCommand,
)
from papervault_api.documents.application.queues import DocumentProcessingQueue
from papervault_api.documents.application.read import DocumentReadService
from papervault_api.documents.application.reprocessing import (
    DocumentReprocessingService,
    InvalidReprocessingRequestError,
    ReprocessingCommand,
    ReprocessingQueueError,
)
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.application.text_search import DocumentTextSearchService
from papervault_api.documents.application.uploads import (
    DocumentUploadService,
    EmptyUploadError,
    UnsupportedUploadTypeError,
    UploadDocumentCommand,
    UploadTooLargeError,
)
from papervault_api.documents.application.versions import (
    DocumentVersionService,
    InvalidVersionChangeError,
    VersionChangeResult,
)
from papervault_api.documents.domain.document_types import (
    UnknownDocumentTypeError,
    list_document_types,
)
from papervault_api.documents.domain.enums import (
    DocumentReviewStatus,
    DocumentSourceKind,
    DocumentStatus,
)
from papervault_api.documents.domain.models import DocumentRecord
from papervault_api.documents.infrastructure.models import Document, DocumentVersion
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.search.api.indexing import reindex_document_best_effort
from papervault_api.tags.application.service import TagService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> list[DocumentResponse]:
    service = DocumentReadService(session)
    documents = await service.list_documents(
        owner_id=current_user.id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return [
        DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)
        for document in documents
    ]


@router.get("/review-queue", response_model=list[DocumentResponse])
async def list_review_queue(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DocumentResponse]:
    documents = await DocumentReadService(session).list_review_queue(
        owner_id=current_user.id,
        limit=limit,
    )
    return [
        DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)
        for document in documents
    ]


@router.get(
    "/duplicates/candidates",
    response_model=list[DuplicateCandidateGroupResponse],
)
async def list_duplicate_candidates(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[DuplicateCandidateGroupResponse]:
    groups = await DuplicateDetectionService(
        session,
        content_similarity_threshold=settings.duplicate_content_similarity_threshold,
        ocr_similarity_threshold=settings.duplicate_ocr_similarity_threshold,
        min_tokens=settings.duplicate_similarity_min_tokens,
    ).list_candidates(current_user.id)
    return [
        DuplicateCandidateGroupResponse(
            method=group.method,
            confidence=group.confidence,
            requires_confirmation=group.requires_confirmation,
            explanation=group.explanation,
            signals=DuplicateSignalsResponse(
                text_similarity=group.signals.text_similarity,
                length_similarity=group.signals.length_similarity,
                shared_bands=group.signals.shared_bands,
            ),
            documents=[
                DuplicateCandidateDocumentResponse(
                    id=document.id,
                    title=document.title,
                    original_filename=document.original_filename,
                    sha256_hash=document.sha256_hash,
                    document_type=document.document_type,
                    file_size_bytes=document.file_size_bytes,
                    page_count=document.page_count,
                    created_at=document.created_at,
                )
                for document in group.documents
            ],
        )
        for group in groups
    ]


@router.post(
    "/duplicates/refresh",
    response_model=RefreshDuplicateFingerprintsResponse,
)
async def refresh_duplicate_fingerprints(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RefreshDuplicateFingerprintsResponse:
    result = await DuplicateDetectionService(
        session,
        content_similarity_threshold=settings.duplicate_content_similarity_threshold,
        ocr_similarity_threshold=settings.duplicate_ocr_similarity_threshold,
        min_tokens=settings.duplicate_similarity_min_tokens,
    ).refresh_owner(current_user.id, limit=limit)
    return RefreshDuplicateFingerprintsResponse(
        scanned=result.scanned,
        updated=result.updated,
        skipped=result.skipped,
    )


@router.post(
    "/duplicates/merge",
    response_model=MergeDuplicateDocumentsResponse,
)
async def merge_duplicate_documents(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: MergeDuplicateDocumentsRequest,
) -> MergeDuplicateDocumentsResponse:
    try:
        result = await DocumentLifecycleService(
            session,
            duplicate_content_similarity_threshold=(
                settings.duplicate_content_similarity_threshold
            ),
            duplicate_ocr_similarity_threshold=(settings.duplicate_ocr_similarity_threshold),
            duplicate_similarity_min_tokens=settings.duplicate_similarity_min_tokens,
        ).merge_duplicates(
            DuplicateMergeCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                keep_document_id=request.keep_document_id,
                duplicate_document_ids=tuple(request.duplicate_document_ids),
                match_method=request.match_method,
                confirm_non_exact=request.confirm_non_exact,
            ),
        )
    except InvalidDuplicateMergeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=result.kept_document.id,
        reason="duplicates_merged",
    )
    for document in result.archived_documents:
        await reindex_document_best_effort(
            session=session,
            settings=settings,
            document_id=document.id,
            reason="duplicate_archived",
        )

    return MergeDuplicateDocumentsResponse(
        kept_document=DocumentResponse.model_validate(
            document_record_from_orm(result.kept_document),
            from_attributes=True,
        ),
        archived_documents=[
            DocumentResponse.model_validate(
                document_record_from_orm(document),
                from_attributes=True,
            )
            for document in result.archived_documents
        ],
    )


@router.get("/types", response_model=list[DocumentTypeResponse])
async def get_document_types() -> list[DocumentTypeResponse]:
    return [
        DocumentTypeResponse(
            key=definition.key,
            label=definition.label,
            metadata_fields=[
                MetadataFieldDefinitionResponse(
                    key=field.key,
                    label=field.label,
                    field_type=field.field_type.value,
                    required=field.required,
                )
                for field in definition.metadata_fields
            ],
        )
        for definition in list_document_types()
    ]


@router.post(
    "/uploads",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    upload_service: Annotated[DocumentUploadService, Depends(get_document_upload_service)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    document_type: Annotated[str, Form()] = "generic_pdf",
) -> UploadDocumentResponse:
    try:
        uploaded = await upload_service.upload_document(
            UploadDocumentCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                filename=file.filename or "document",
                content_type=file.content_type or "application/octet-stream",
                title=title,
                document_type=document_type,
            ),
            file,
        )
    except UnsupportedUploadTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except EmptyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnknownDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return UploadDocumentResponse(
        document=DocumentResponse.model_validate(uploaded.document, from_attributes=True),
        processing_task_id=uploaded.processing_task_id,
    )


@router.post("/{document_id}/reprocess", response_model=ReprocessDocumentResponse)
async def reprocess_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    processing_queue: Annotated[
        DocumentProcessingQueue,
        Depends(get_document_processing_queue),
    ],
) -> ReprocessDocumentResponse:
    try:
        result = await DocumentReprocessingService(session, processing_queue).request(
            ReprocessingCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                document_id=document_id,
            )
        )
    except InvalidReprocessingRequestError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReprocessingQueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return ReprocessDocumentResponse(
        document=DocumentResponse.model_validate(
            document_record_from_orm(result.document),
            from_attributes=True,
        ),
        processing_task_id=result.processing_task_id,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentDetailResponse:
    service = DocumentReadService(session)
    detail = await service.get_detail(document_id=document_id, owner_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return DocumentDetailResponse(
        document=DocumentResponse.model_validate(
            document_record_from_orm(detail.document),
            from_attributes=True,
        ),
        ai_analysis=(
            AIAnalysisResponse(
                provider=detail.current_ai_analysis.provider,
                model=detail.current_ai_analysis.model,
                summary=detail.current_ai_analysis.summary,
                keywords=detail.current_ai_analysis.keywords,
                entities=detail.current_ai_analysis.entities,
                suggested_tags=detail.current_ai_analysis.suggested_tags,
                category=detail.current_ai_analysis.category,
                confidence_score=float(detail.current_ai_analysis.confidence_score)
                if detail.current_ai_analysis.confidence_score is not None
                else None,
            )
            if detail.current_ai_analysis is not None
            else None
        ),
        metadata=(
            MetadataResponse(
                schema_name=detail.current_metadata.schema_name,
                schema_version=detail.current_metadata.schema_version,
                data=detail.current_metadata.data,
                confidence_score=float(detail.current_metadata.confidence_score)
                if detail.current_metadata.confidence_score is not None
                else None,
            )
            if detail.current_metadata is not None
            else None
        ),
        text_extraction=(
            TextExtractionResponse(
                status=detail.current_text_extraction.status,
                source=detail.current_text_extraction.source,
                page_count=detail.current_text_extraction.page_count,
                language=detail.current_text_extraction.language,
                error_message=detail.current_text_extraction.error_message,
            )
            if detail.current_text_extraction is not None
            else None
        ),
        tags=[
            DocumentTagResponse(
                id=tag.id,
                name=tag.name,
                slug=tag.slug,
                color=tag.color,
            )
            for tag in detail.tags
        ],
        timeline_events=[
            TimelineEventResponse(
                id=event.id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for event in detail.timeline_events
        ],
        versions=[
            DocumentVersionResponse(
                id=version.id,
                version_number=version.version_number,
                original_filename=version.original_filename,
                content_type=version.content_type,
                sha256_hash=version.sha256_hash,
                file_size_bytes=version.file_size_bytes,
                change_reason=version.change_reason,
                is_current=version.is_current,
                created_by_id=version.created_by_id,
                created_at=version.created_at,
            )
            for version in detail.versions
        ],
    )


@router.post("/{document_id}/versions", response_model=VersionChangeResponse)
async def replace_document_source(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    queue: Annotated[DocumentProcessingQueue, Depends(get_document_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    change_reason: Annotated[str | None, Form(max_length=255)] = None,
) -> VersionChangeResponse:
    service = document_version_service(session, storage, queue, settings)
    try:
        result = await service.replace_source(
            owner_id=current_user.id,
            actor_id=current_user.id,
            document_id=document_id,
            filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            stream=file,
            change_reason=change_reason,
        )
    except UnsupportedUploadTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except EmptyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InvalidVersionChangeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="document_source_replaced",
    )
    return version_change_response(result)


@router.post(
    "/{document_id}/versions/{version_id}/restore",
    response_model=VersionChangeResponse,
)
async def restore_document_version(
    document_id: UUID,
    version_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    queue: Annotated[DocumentProcessingQueue, Depends(get_document_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionChangeResponse:
    service = document_version_service(session, storage, queue, settings)
    try:
        result = await service.restore_version(
            owner_id=current_user.id,
            actor_id=current_user.id,
            document_id=document_id,
            version_id=version_id,
        )
    except InvalidVersionChangeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="document_version_restored",
    )
    return version_change_response(result)


@router.get(
    "/{document_id}/versions/compare",
    response_model=VersionComparisonResponse,
)
async def compare_document_versions(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    queue: Annotated[DocumentProcessingQueue, Depends(get_document_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    from_version: Annotated[UUID, Query()],
    to_version: Annotated[UUID, Query()],
) -> VersionComparisonResponse:
    try:
        comparison = await document_version_service(
            session, storage, queue, settings
        ).compare_versions(
            owner_id=current_user.id,
            document_id=document_id,
            from_version_id=from_version,
            to_version_id=to_version,
        )
    except InvalidVersionChangeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return VersionComparisonResponse(
        from_version=comparison.from_version.version_number,
        to_version=comparison.to_version.version_number,
        source_changed=comparison.source_changed,
        text_available=comparison.text_available,
        added_lines=comparison.added_lines,
        removed_lines=comparison.removed_lines,
        diff_lines=list(comparison.diff_lines),
    )


@router.get("/{document_id}/versions/{version_id}/file")
async def get_document_version_file(
    document_id: UUID,
    version_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    queue: Annotated[DocumentProcessingQueue, Depends(get_document_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    version = await document_version_service(session, storage, queue, settings).get_version(
        owner_id=current_user.id,
        document_id=document_id,
        version_id=version_id,
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    with NamedTemporaryFile(prefix="papervault-version-", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    await storage.download_to_file(
        bucket=version.storage_bucket,
        key=version.storage_key,
        destination=temp_path,
    )
    return FileResponse(
        temp_path,
        media_type=version.content_type,
        filename=version.original_filename,
        content_disposition_type="attachment",
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
    )


@router.get("/{document_id}/text-search", response_model=DocumentTextSearchResponse)
async def search_document_text(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    query: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DocumentTextSearchResponse:
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query must contain at least 2 non-whitespace characters",
        )
    result = await DocumentTextSearchService(session).search(
        owner_id=current_user.id,
        document_id=document_id,
        query=normalized_query,
        limit=limit,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentTextSearchResponse(
        query=result.query,
        total_matches=result.total_matches,
        matches=[
            DocumentTextMatchResponse(
                page_number=match.page_number,
                before=match.before,
                match=match.match,
                after=match.after,
            )
            for match in result.matches
        ],
        page_mapping_available=result.page_mapping_available,
    )


@router.get("/{document_id}/ocr-blocks", response_model=list[OcrTextBlockResponse])
async def get_document_ocr_blocks(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)],
    query: Annotated[str | None, Query(max_length=200)] = None,
) -> list[OcrTextBlockResponse]:
    blocks = await DocumentReadService(session).list_ocr_blocks(
        owner_id=current_user.id,
        document_id=document_id,
        page_number=page,
        query=query,
    )
    if blocks is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return [
        OcrTextBlockResponse(
            text=block.text,
            page_number=block.page_number,
            left_ratio=float(block.left_ratio),
            top_ratio=float(block.top_ratio),
            width_ratio=float(block.width_ratio),
            height_ratio=float(block.height_ratio),
            confidence_score=(
                float(block.confidence_score) if block.confidence_score is not None else None
            ),
        )
        for block in blocks
    ]


@router.patch("/{document_id}/review", response_model=DocumentResponse)
async def update_document_review(
    document_id: UUID,
    request: ReviewDocumentRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    try:
        document = await DocumentLifecycleService(session).update_review(
            ReviewUpdateCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                document_id=document_id,
                status=DocumentReviewStatus(request.status),
                note=request.note,
            )
        )
    except InvalidMetadataError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document.id,
        reason="document_review_updated",
    )
    return DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: UpdateDocumentRequest,
) -> DocumentResponse:
    service = DocumentLifecycleService(session)
    try:
        document = await service.update_document(
            DocumentUpdateCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                document_id=document_id,
                updates=request.model_dump(exclude_unset=True),
            ),
        )
    except UnknownDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await TagService(session).synchronize_document(
        owner_id=current_user.id,
        document_id=document.id,
        actor_id=current_user.id,
    )
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document.id,
        reason="document_fields_updated",
    )
    return DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)


@router.put("/{document_id}/metadata", response_model=MetadataResponse)
async def replace_document_metadata(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: UpdateMetadataRequest,
) -> MetadataResponse:
    service = DocumentLifecycleService(session)
    try:
        metadata = await service.replace_metadata(
            MetadataUpdateCommand(
                owner_id=current_user.id,
                actor_id=current_user.id,
                document_id=document_id,
                schema_name=request.schema_name,
                data=request.data,
                document_date=request.document_date,
                issuer=request.issuer,
                organization=request.organization,
                locale=settings.metadata_locale,
            ),
        )
    except InvalidMetadataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnknownDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await TagService(session).synchronize_document(
        owner_id=current_user.id,
        document_id=document_id,
        actor_id=current_user.id,
    )
    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="metadata_replaced",
    )
    return MetadataResponse(
        schema_name=metadata.schema_name,
        schema_version=metadata.schema_version,
        data=metadata.data,
        confidence_score=float(metadata.confidence_score)
        if metadata.confidence_score is not None
        else None,
    )


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    document = await DocumentLifecycleService(session).archive_document(
        owner_id=current_user.id,
        actor_id=current_user.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document.id,
        reason="document_archived",
    )
    return DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    download: bool = Query(default=False),
) -> FileResponse:
    service = DocumentReadService(session)
    document = await service.get_document_file(document_id=document_id, owner_id=current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    with NamedTemporaryFile(prefix="papervault-viewer-", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    await storage.download_to_file(
        bucket=document.storage_bucket,
        key=document.storage_key,
        destination=temp_path,
    )
    return FileResponse(
        temp_path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="attachment" if download else "inline",
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    deleted = await DocumentDeletionService(session=session, storage=storage).delete_document(
        owner_id=current_user.id,
        document_id=document_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await reindex_document_best_effort(
        session=session,
        settings=settings,
        document_id=document_id,
        reason="document_deleted",
    )


@router.get("/{document_id}/timeline", response_model=list[TimelineEventResponse])
async def get_document_timeline(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TimelineEventResponse]:
    service = DocumentReadService(session)
    detail = await service.get_detail(document_id=document_id, owner_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return [
        TimelineEventResponse(
            id=event.id,
            event_type=event.event_type,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )
        for event in detail.timeline_events
    ]


def document_record_from_orm(document: Document) -> DocumentRecord:
    return DocumentRecord(
        id=document.id,
        owner_id=document.owner_id,
        title=document.title,
        original_filename=document.original_filename,
        content_type=document.content_type,
        file_size_bytes=document.file_size_bytes,
        sha256_hash=document.sha256_hash,
        storage_bucket=document.storage_bucket,
        storage_key=document.storage_key,
        source_kind=DocumentSourceKind(document.source_kind),
        status=DocumentStatus(document.status),
        document_type=document.document_type,
        document_date=document.document_date,
        issuer=document.issuer,
        organization=document.organization,
        processing_error=document.processing_error,
        processing_started_at=document.processing_started_at,
        processing_completed_at=document.processing_completed_at,
        review_status=DocumentReviewStatus(document.review_status),
        review_reasons=tuple(document.review_reasons),
        reviewed_at=document.reviewed_at,
        reviewed_by_id=document.reviewed_by_id,
        review_note=document.review_note,
        archived_at=document.archived_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def document_version_service(
    session: AsyncSession,
    storage: ObjectStorage,
    queue: DocumentProcessingQueue,
    settings: Settings,
) -> DocumentVersionService:
    return DocumentVersionService(
        session=session,
        storage=storage,
        processing_queue=queue,
        bucket_name=settings.s3_bucket_documents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
    )


def document_version_response(version: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        content_type=version.content_type,
        sha256_hash=version.sha256_hash,
        file_size_bytes=version.file_size_bytes,
        change_reason=version.change_reason,
        is_current=version.is_current,
        created_by_id=version.created_by_id,
        created_at=version.created_at,
    )


def version_change_response(result: VersionChangeResult) -> VersionChangeResponse:
    return VersionChangeResponse(
        document=DocumentResponse.model_validate(
            document_record_from_orm(result.document),
            from_attributes=True,
        ),
        version=document_version_response(result.version),
        processing_task_id=result.processing_task_id,
    )
