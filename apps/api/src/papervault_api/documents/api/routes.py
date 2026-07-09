from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from papervault_api.core.config import Settings, get_settings
from papervault_api.db.session import get_session
from papervault_api.documents.api.dependencies import (
    get_document_upload_service,
    get_object_storage,
)
from papervault_api.documents.api.schemas import (
    AIAnalysisResponse,
    DocumentDetailResponse,
    DocumentResponse,
    DocumentTagResponse,
    DocumentTypeResponse,
    DocumentVersionResponse,
    DuplicateCandidateDocumentResponse,
    DuplicateCandidateGroupResponse,
    MetadataFieldDefinitionResponse,
    MetadataResponse,
    TextExtractionResponse,
    TimelineEventResponse,
    UpdateDocumentRequest,
    UpdateMetadataRequest,
    UploadDocumentResponse,
)
from papervault_api.documents.application.lifecycle import (
    DocumentLifecycleService,
    DocumentUpdateCommand,
    InvalidMetadataError,
    MetadataUpdateCommand,
)
from papervault_api.documents.application.read import DocumentReadService
from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.application.uploads import (
    DocumentUploadService,
    EmptyUploadError,
    UnsupportedUploadTypeError,
    UploadDocumentCommand,
    UploadTooLargeError,
)
from papervault_api.documents.domain.document_types import (
    UnknownDocumentTypeError,
    list_document_types,
)
from papervault_api.documents.domain.enums import DocumentSourceKind, DocumentStatus
from papervault_api.documents.domain.models import DocumentRecord
from papervault_api.documents.infrastructure.models import Document
from papervault_api.identity.api.dependencies import get_current_user
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.search.application.indexing import SearchIndexingService
from papervault_api.search.infrastructure.opensearch import (
    OpenSearchError,
    build_search_document_index,
)

router = APIRouter(prefix="/documents", tags=["documents"])
logger = structlog.get_logger(__name__)


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


@router.get(
    "/duplicates/candidates",
    response_model=list[DuplicateCandidateGroupResponse],
)
async def list_duplicate_candidates(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DuplicateCandidateGroupResponse]:
    service = DocumentReadService(session)
    groups = await service.get_duplicate_candidates(current_user.id)
    return [
        DuplicateCandidateGroupResponse(
            method="sha256_hash",
            documents=[
                DuplicateCandidateDocumentResponse(
                    id=document.id,
                    title=document.title,
                    original_filename=document.original_filename,
                    sha256_hash=document.sha256_hash,
                    created_at=document.created_at,
                )
                for document in group
            ],
        )
        for group in groups
    ]


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
                sha256_hash=version.sha256_hash,
                file_size_bytes=version.file_size_bytes,
                change_reason=version.change_reason,
                created_by_id=version.created_by_id,
                created_at=version.created_at,
            )
            for version in detail.versions
        ],
    )


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

    await reindex_document_best_effort(session=session, settings=settings, document_id=document.id)
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
            ),
        )
    except InvalidMetadataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await reindex_document_best_effort(session=session, settings=settings, document_id=document_id)
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

    await reindex_document_best_effort(session=session, settings=settings, document_id=document.id)
    return DocumentResponse.model_validate(document_record_from_orm(document), from_attributes=True)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
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
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
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
        archived_at=document.archived_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def reindex_document_best_effort(
    *,
    session: AsyncSession,
    settings: Settings,
    document_id: UUID,
) -> None:
    service = SearchIndexingService(
        session=session,
        search_index=build_search_document_index(settings),
    )
    try:
        await service.index_document(document_id)
    except OpenSearchError as exc:
        logger.warning(
            "document_lifecycle_search_indexing_failed",
            document_id=str(document_id),
            error=str(exc),
        )
