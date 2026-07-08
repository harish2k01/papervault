from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from papervault_api.documents.domain.enums import DocumentSourceKind, DocumentStatus


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
