from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import Document, DocumentMetadataRecord
from papervault_api.notifications.domain.enums import NotificationKind, NotificationStatus
from papervault_api.notifications.infrastructure.models import Notification

DATE_FIELD_KIND = {
    "due_date": NotificationKind.DUE_DATE,
    "expiry_date": NotificationKind.EXPIRY,
    "renewal_date": NotificationKind.POLICY_RENEWAL,
    "warranty_expiry_date": NotificationKind.WARRANTY_EXPIRY,
}


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_for_document(self, document_id: UUID) -> tuple[Notification, ...]:
        document = await self._session.get(Document, document_id)
        if document is None:
            return ()

        metadata = await self._get_current_metadata(document_id)
        if metadata is None:
            return ()

        notifications: list[Notification] = []
        for field_name, kind in DATE_FIELD_KIND.items():
            due_date = parse_date(metadata.data.get(field_name))
            if due_date is None:
                continue
            notification = await self._upsert_notification(
                document=document,
                kind=kind,
                due_date=due_date,
                source_field=field_name,
            )
            notifications.append(notification)

        await self._session.commit()
        return tuple(notifications)

    async def list_notifications(
        self,
        owner_id: UUID,
        status: NotificationStatus | None = None,
    ) -> tuple[Notification, ...]:
        statement = select(Notification).where(Notification.owner_id == owner_id)
        if status is not None:
            statement = statement.where(Notification.status == status.value)
        result = await self._session.execute(
            statement.order_by(Notification.due_date.asc(), Notification.created_at.desc()),
        )
        return tuple(result.scalars())

    async def update_status(
        self,
        *,
        owner_id: UUID,
        notification_id: UUID,
        status: NotificationStatus,
    ) -> Notification | None:
        notification = await self._session.get(Notification, notification_id)
        if notification is None or notification.owner_id != owner_id:
            return None
        notification.status = status.value
        await self._session.commit()
        await self._session.refresh(notification)
        return notification

    async def _get_current_metadata(self, document_id: UUID) -> DocumentMetadataRecord | None:
        result = await self._session.execute(
            select(DocumentMetadataRecord).where(
                DocumentMetadataRecord.document_id == document_id,
                DocumentMetadataRecord.is_current.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def _upsert_notification(
        self,
        *,
        document: Document,
        kind: NotificationKind,
        due_date: date,
        source_field: str,
    ) -> Notification:
        result = await self._session.execute(
            select(Notification).where(
                Notification.owner_id == document.owner_id,
                Notification.document_id == document.id,
                Notification.kind == kind.value,
                Notification.due_date == due_date,
            ),
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        notification = Notification(
            owner_id=document.owner_id,
            document_id=document.id,
            kind=kind.value,
            title=notification_title(kind, document.title),
            message=notification_message(kind, document.title, due_date),
            due_date=due_date,
            payload={"source_field": source_field, "document_type": document.document_type},
        )
        self._session.add(notification)
        await self._session.flush()
        return notification


def notification_title(kind: NotificationKind, document_title: str) -> str:
    label = {
        NotificationKind.DUE_DATE: "Upcoming due date",
        NotificationKind.EXPIRY: "Document expiry",
        NotificationKind.POLICY_RENEWAL: "Policy renewal",
        NotificationKind.WARRANTY_EXPIRY: "Warranty expiry",
    }[kind]
    return f"{label}: {document_title}"


def notification_message(kind: NotificationKind, document_title: str, due_date: date) -> str:
    label = kind.value.replace("_", " ")
    return f"{document_title} has {label} on {due_date.isoformat()}."


def parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for format_string in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            continue
    return None
