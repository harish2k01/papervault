from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from papervault_api.documents.domain.enums import (
    DocumentReviewStatus,
    DocumentSourceKind,
    DocumentStatus,
)


@dataclass(frozen=True, slots=True)
class NewDocumentRecord:
    owner_id: UUID
    title: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    sha256_hash: str
    storage_bucket: str
    storage_key: str
    source_kind: DocumentSourceKind = DocumentSourceKind.UPLOAD
    document_type: str = "generic_pdf"
    document_date: date | None = None
    issuer: str | None = None
    organization: str | None = None
    storage_version_id: str | None = None
    page_count: int | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: UUID
    owner_id: UUID
    title: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    sha256_hash: str
    storage_bucket: str
    storage_key: str
    source_kind: DocumentSourceKind
    status: DocumentStatus
    document_type: str
    created_at: datetime
    updated_at: datetime
    document_date: date | None = None
    issuer: str | None = None
    organization: str | None = None
    processing_error: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    review_status: DocumentReviewStatus = DocumentReviewStatus.NOT_REQUIRED
    review_reasons: tuple[str, ...] = ()
    reviewed_at: datetime | None = None
    reviewed_by_id: UUID | None = None
    review_note: str | None = None
    archived_at: datetime | None = None
