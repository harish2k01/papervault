import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.duplicates import (
    EXACT_FILE_METHOD,
    DuplicateDetectionService,
)
from papervault_api.documents.domain.document_types import get_document_type
from papervault_api.documents.domain.enums import (
    DocumentReviewStatus,
    DocumentStatus,
    MetadataSource,
)
from papervault_api.documents.domain.metadata import normalize_document_metadata
from papervault_api.documents.infrastructure.models import Document, DocumentMetadataRecord
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent


class InvalidMetadataError(ValueError):
    pass


class InvalidDuplicateMergeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentUpdateCommand:
    owner_id: UUID
    actor_id: UUID
    document_id: UUID
    updates: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MetadataUpdateCommand:
    owner_id: UUID
    actor_id: UUID
    document_id: UUID
    data: dict[str, Any]
    schema_name: str | None = None
    document_date: date | None = None
    issuer: str | None = None
    organization: str | None = None
    locale: str = "en-IN"


@dataclass(frozen=True, slots=True)
class DuplicateMergeCommand:
    owner_id: UUID
    actor_id: UUID
    keep_document_id: UUID
    duplicate_document_ids: tuple[UUID, ...]
    match_method: str = EXACT_FILE_METHOD
    confirm_non_exact: bool = False


@dataclass(frozen=True, slots=True)
class ReviewUpdateCommand:
    owner_id: UUID
    actor_id: UUID
    document_id: UUID
    status: DocumentReviewStatus
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DuplicateMergeResult:
    kept_document: Document
    archived_documents: tuple[Document, ...]


class DocumentLifecycleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        duplicate_content_similarity_threshold: float = 0.88,
        duplicate_ocr_similarity_threshold: float = 0.84,
        duplicate_similarity_min_tokens: int = 24,
    ) -> None:
        self._session = session
        self._duplicate_detector = DuplicateDetectionService(
            session,
            content_similarity_threshold=duplicate_content_similarity_threshold,
            ocr_similarity_threshold=duplicate_ocr_similarity_threshold,
            min_tokens=duplicate_similarity_min_tokens,
        )

    async def update_document(self, command: DocumentUpdateCommand) -> Document | None:
        document = await self._get_document(command.document_id, command.owner_id)
        if document is None:
            return None

        changed_fields: list[str] = []
        updates = command.updates
        if "title" in updates:
            document.title = (
                normalize_optional_string(updates["title"], max_length=255) or document.title
            )
            changed_fields.append("title")
        if "document_type" in updates:
            document_type = normalize_optional_string(updates["document_type"], max_length=80)
            if document_type is not None:
                get_document_type(document_type)
                document.document_type = document_type
                changed_fields.append("document_type")
        if "document_date" in updates:
            document.document_date = updates["document_date"]
            changed_fields.append("document_date")
        if "issuer" in updates:
            document.issuer = normalize_optional_string(updates["issuer"], max_length=255)
            changed_fields.append("issuer")
        if "organization" in updates:
            document.organization = normalize_optional_string(
                updates["organization"], max_length=255
            )
            changed_fields.append("organization")

        if changed_fields:
            document.review_status = DocumentReviewStatus.PENDING.value
            document.review_reasons = ["manual_change:document_fields"]
            document.reviewed_at = None
            document.reviewed_by_id = None
            document.review_note = None
            self._session.add(
                TimelineEvent(
                    owner_id=command.owner_id,
                    actor_id=command.actor_id,
                    document_id=command.document_id,
                    event_type=TimelineEventType.METADATA_EDITED.value,
                    payload={"action": "document_fields_updated", "fields": changed_fields},
                ),
            )
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def replace_metadata(
        self,
        command: MetadataUpdateCommand,
    ) -> DocumentMetadataRecord | None:
        document = await self._get_document(command.document_id, command.owner_id)
        if document is None:
            return None

        validate_json_object(command.data)
        schema_name = command.schema_name or document.document_type
        normalized_metadata = normalize_document_metadata(
            schema_name,
            command.data,
            locale=command.locale,
        )
        current_metadata = await self._current_metadata(command.document_id)
        current_schema_version = (
            current_metadata.schema_version if current_metadata is not None else 1
        )
        if current_metadata is not None:
            current_metadata.is_current = False

        record = DocumentMetadataRecord(
            document_id=document.id,
            schema_name=schema_name,
            schema_version=current_schema_version,
            data=normalized_metadata.data,
            source=MetadataSource.MANUAL.value,
            confidence_score=None,
            extractor="manual",
            extracted_at=datetime.now(UTC),
            is_current=True,
        )
        self._session.add(record)

        derived = derive_document_fields(normalized_metadata.data)
        document.document_date = (
            command.document_date if command.document_date is not None else derived.document_date
        )
        document.issuer = command.issuer if command.issuer is not None else derived.issuer
        document.organization = (
            command.organization if command.organization is not None else derived.organization
        )
        document.review_status = DocumentReviewStatus.PENDING.value
        document.review_reasons = [
            f"{issue.code}:{issue.field}" for issue in normalized_metadata.issues
        ] or ["manual_change:metadata"]
        document.reviewed_at = None
        document.reviewed_by_id = None
        document.review_note = None

        self._session.add(
            TimelineEvent(
                owner_id=command.owner_id,
                actor_id=command.actor_id,
                document_id=command.document_id,
                event_type=TimelineEventType.METADATA_EDITED.value,
                payload={
                    "action": "metadata_replaced",
                    "schema_name": schema_name,
                    "keys": sorted(normalized_metadata.data),
                },
            ),
        )
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def update_review(self, command: ReviewUpdateCommand) -> Document | None:
        document = await self._get_document(command.document_id, command.owner_id)
        if document is None:
            return None
        if document.status == DocumentStatus.ARCHIVED.value:
            raise InvalidMetadataError("Archived documents cannot be reviewed")

        document.review_status = command.status.value
        document.review_note = normalize_optional_string(command.note, max_length=1000)
        if command.status is DocumentReviewStatus.APPROVED:
            document.review_reasons = []
            document.reviewed_at = datetime.now(UTC)
            document.reviewed_by_id = command.actor_id
        else:
            document.review_reasons = document.review_reasons or ["manual_review_requested"]
            document.reviewed_at = None
            document.reviewed_by_id = None

        self._session.add(
            TimelineEvent(
                owner_id=command.owner_id,
                actor_id=command.actor_id,
                document_id=command.document_id,
                event_type=TimelineEventType.METADATA_EDITED.value,
                payload={
                    "action": "review_status_changed",
                    "review_status": command.status.value,
                    "note_present": bool(document.review_note),
                },
            )
        )
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def archive_document(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        document = await self._get_document(document_id, owner_id)
        if document is None:
            return None

        if document.status != DocumentStatus.ARCHIVED.value:
            document.status = DocumentStatus.ARCHIVED.value
            document.archived_at = datetime.now(UTC)
            self._session.add(
                TimelineEvent(
                    owner_id=owner_id,
                    actor_id=actor_id,
                    document_id=document_id,
                    event_type=TimelineEventType.DOCUMENT_ARCHIVED.value,
                    payload={"action": "archived"},
                ),
            )

        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def merge_duplicates(
        self,
        command: DuplicateMergeCommand,
    ) -> DuplicateMergeResult | None:
        duplicate_ids = tuple(dict.fromkeys(command.duplicate_document_ids))
        if not duplicate_ids:
            raise InvalidDuplicateMergeError("At least one duplicate document is required")
        if command.keep_document_id in duplicate_ids:
            raise InvalidDuplicateMergeError("Keep document cannot be archived")

        requested_ids = {command.keep_document_id, *duplicate_ids}
        documents = (
            await self._session.execute(
                select(Document).where(
                    Document.owner_id == command.owner_id,
                    Document.id.in_(requested_ids),
                ),
            )
        ).scalars()
        documents_by_id = {document.id: document for document in documents}
        if set(documents_by_id) != requested_ids:
            return None

        kept_document = documents_by_id[command.keep_document_id]
        duplicate_documents = tuple(documents_by_id[document_id] for document_id in duplicate_ids)
        if kept_document.status == DocumentStatus.ARCHIVED.value or any(
            document.status == DocumentStatus.ARCHIVED.value for document in duplicate_documents
        ):
            raise InvalidDuplicateMergeError("Archived documents cannot be merged")
        validations = []
        for document in duplicate_documents:
            validation = await self._duplicate_detector.validate_pair(
                owner_id=command.owner_id,
                keep_document=kept_document,
                duplicate_document=document,
                requested_method=command.match_method,
            )
            if validation is None:
                raise InvalidDuplicateMergeError(
                    "Documents no longer meet the selected duplicate threshold"
                )
            if validation.requires_confirmation and not command.confirm_non_exact:
                raise InvalidDuplicateMergeError(
                    "Non-exact duplicate matches require explicit confirmation"
                )
            validations.append(validation)

        archived_at = datetime.now(UTC)
        for document, validation in zip(duplicate_documents, validations, strict=True):
            document.status = DocumentStatus.ARCHIVED.value
            document.archived_at = archived_at
            self._session.add(
                TimelineEvent(
                    owner_id=command.owner_id,
                    actor_id=command.actor_id,
                    document_id=document.id,
                    event_type=TimelineEventType.DOCUMENT_ARCHIVED.value,
                    payload={
                        "action": "duplicate_merged",
                        "kept_document_id": str(kept_document.id),
                        "match_method": validation.method,
                        "confidence": validation.confidence,
                    },
                ),
            )

        self._session.add(
            TimelineEvent(
                owner_id=command.owner_id,
                actor_id=command.actor_id,
                document_id=kept_document.id,
                event_type=TimelineEventType.METADATA_EDITED.value,
                payload={
                    "action": "duplicates_merged",
                    "archived_document_ids": [str(document.id) for document in duplicate_documents],
                    "match_method": command.match_method,
                    "confidence_scores": [validation.confidence for validation in validations],
                },
            ),
        )

        await self._session.commit()
        await self._session.refresh(kept_document)
        for document in duplicate_documents:
            await self._session.refresh(document)
        return DuplicateMergeResult(
            kept_document=kept_document,
            archived_documents=duplicate_documents,
        )

    async def _get_document(self, document_id: UUID, owner_id: UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id),
        )
        return result.scalar_one_or_none()

    async def _current_metadata(self, document_id: UUID) -> DocumentMetadataRecord | None:
        result = await self._session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document_id,
                DocumentMetadataRecord.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class DerivedDocumentFields:
    document_date: date | None = None
    issuer: str | None = None
    organization: str | None = None


def derive_document_fields(data: Mapping[str, Any]) -> DerivedDocumentFields:
    issuer = first_string_value(
        data,
        "issuer",
        "provider",
        "vendor",
        "bank",
        "employer",
        "organization",
    )
    organization = first_string_value(
        data,
        "organization",
        "provider",
        "vendor",
        "bank",
        "employer",
    )
    document_date = first_date_value(
        data,
        "document_date",
        "purchase_date",
        "invoice_date",
        "statement_date",
        "due_date",
        "expiry_date",
        "date",
    ) or month_year_date(data)
    return DerivedDocumentFields(
        document_date=document_date,
        issuer=issuer,
        organization=organization,
    )


def first_string_value(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
    return None


def first_date_value(data: Mapping[str, Any], *keys: str) -> date | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                continue
    return None


def month_year_date(data: Mapping[str, Any]) -> date | None:
    try:
        year = int(data["year"])
        month = int(data["month"])
    except (KeyError, TypeError, ValueError):
        return None
    if month < 1 or month > 12:
        return None
    return date(year, month, 1)


def normalize_optional_string(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def validate_json_object(data: dict[str, Any]) -> None:
    try:
        json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise InvalidMetadataError("Metadata must be a JSON-serializable object") from exc
