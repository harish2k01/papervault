from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.collections.domain.enums import CollectionKind, CollectionView
from papervault_api.collections.infrastructure.models import (
    CollectionDocument,
    VaultCollection,
)
from papervault_api.documents.application.rules import (
    apply_document_rule,
    case_insensitive_contains,
)
from papervault_api.documents.domain.document_types import get_document_type
from papervault_api.documents.domain.enums import DocumentStatus
from papervault_api.documents.domain.rules import DocumentRule
from papervault_api.documents.infrastructure.models import Document
from papervault_api.timeline.domain.events import TimelineEventType
from papervault_api.timeline.infrastructure.models import TimelineEvent

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class CollectionConflictError(ValueError):
    pass


class InvalidCollectionOperationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    collection: VaultCollection
    document_count: int


@dataclass(frozen=True, slots=True)
class CollectionDocumentPage:
    documents: tuple[Document, ...]
    total: int


class CollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_collections(self, owner_id: UUID) -> tuple[CollectionSummary, ...]:
        collections = tuple(
            (
                await self._session.execute(
                    select(VaultCollection)
                    .where(VaultCollection.owner_id == owner_id)
                    .order_by(VaultCollection.name.asc()),
                )
            ).scalars(),
        )
        if not collections:
            return ()

        manual_counts = {
            collection_id: int(count)
            for collection_id, count in (
                await self._session.execute(
                    select(CollectionDocument.collection_id, func.count(Document.id))
                    .join(Document, Document.id == CollectionDocument.document_id)
                    .where(
                        CollectionDocument.collection_id.in_(
                            collection.id for collection in collections
                        ),
                        Document.status != DocumentStatus.ARCHIVED.value,
                    )
                    .group_by(CollectionDocument.collection_id),
                )
            ).all()
        }

        summaries: list[CollectionSummary] = []
        for collection in collections:
            if collection.kind == CollectionKind.MANUAL.value:
                count = manual_counts.get(collection.id, 0)
            else:
                count = await self._count_dynamic_documents(
                    owner_id,
                    DocumentRule.from_mapping(collection.rule),
                )
            summaries.append(CollectionSummary(collection=collection, document_count=count))
        return tuple(summaries)

    async def get_collection(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
    ) -> VaultCollection | None:
        result = await self._session.execute(
            select(VaultCollection).where(
                VaultCollection.id == collection_id,
                VaultCollection.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_collection(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        name: str,
        kind: CollectionKind,
        description: str | None = None,
        color: str | None = None,
        view_mode: CollectionView = CollectionView.GRID,
        rule: DocumentRule | None = None,
    ) -> CollectionSummary:
        normalized_name = name.strip()
        if not normalized_name:
            raise InvalidCollectionOperationError("Collection name cannot be empty")
        slug = slugify_collection(normalized_name)
        if await self._collection_slug_exists(owner_id, slug):
            raise CollectionConflictError("A collection with this name already exists")

        normalized_rule = rule or DocumentRule()
        validate_collection_rule(kind, normalized_rule)
        collection = VaultCollection(
            owner_id=owner_id,
            name=normalized_name,
            slug=slug,
            description=normalize_optional(description, 500),
            color=normalize_optional(color, 20),
            kind=kind.value,
            view_mode=view_mode.value,
            rule=normalized_rule.as_dict() if kind is CollectionKind.DYNAMIC else {},
        )
        self._session.add(collection)
        await self._session.flush()
        self._session.add(
            TimelineEvent(
                owner_id=owner_id,
                actor_id=actor_id,
                document_id=None,
                event_type=TimelineEventType.COLLECTIONS_CHANGED.value,
                payload={
                    "action": "collection_created",
                    "collection_id": str(collection.id),
                    "collection": collection.slug,
                    "kind": collection.kind,
                },
            ),
        )
        await self._session.commit()
        await self._session.refresh(collection)
        count = (
            await self._count_dynamic_documents(owner_id, normalized_rule)
            if kind is CollectionKind.DYNAMIC
            else 0
        )
        return CollectionSummary(collection=collection, document_count=count)

    async def update_collection(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        collection_id: UUID,
        updates: Mapping[str, Any],
    ) -> CollectionSummary | None:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        if collection is None:
            return None

        changed: list[str] = []
        if "name" in updates and updates["name"] is not None:
            name = str(updates["name"]).strip()
            if not name:
                raise InvalidCollectionOperationError("Collection name cannot be empty")
            slug = slugify_collection(name)
            if slug != collection.slug and await self._collection_slug_exists(owner_id, slug):
                raise CollectionConflictError("A collection with this name already exists")
            collection.name = name
            collection.slug = slug
            changed.append("name")
        if "description" in updates:
            collection.description = normalize_optional(updates["description"], 500)
            changed.append("description")
        if "color" in updates:
            collection.color = normalize_optional(updates["color"], 20)
            changed.append("color")
        if "view_mode" in updates and updates["view_mode"] is not None:
            collection.view_mode = CollectionView(updates["view_mode"]).value
            changed.append("view_mode")
        if "rule" in updates and updates["rule"] is not None:
            if collection.kind != CollectionKind.DYNAMIC.value:
                raise InvalidCollectionOperationError(
                    "Only dynamic collections can have matching rules"
                )
            rule = DocumentRule.from_mapping(updates["rule"])
            validate_collection_rule(CollectionKind.DYNAMIC, rule)
            collection.rule = rule.as_dict()
            changed.append("rule")

        if changed:
            self._session.add(
                TimelineEvent(
                    owner_id=owner_id,
                    actor_id=actor_id,
                    document_id=None,
                    event_type=TimelineEventType.COLLECTIONS_CHANGED.value,
                    payload={
                        "action": "collection_updated",
                        "collection_id": str(collection.id),
                        "collection": collection.slug,
                        "fields": changed,
                    },
                ),
            )
        await self._session.commit()
        await self._session.refresh(collection)
        count = await self._count_collection_documents(owner_id, collection)
        return CollectionSummary(collection=collection, document_count=count)

    async def delete_collection(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        collection_id: UUID,
    ) -> bool:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        if collection is None:
            return False
        self._session.add(
            TimelineEvent(
                owner_id=owner_id,
                actor_id=actor_id,
                document_id=None,
                event_type=TimelineEventType.COLLECTIONS_CHANGED.value,
                payload={
                    "action": "collection_deleted",
                    "collection_id": str(collection.id),
                    "collection": collection.slug,
                },
            ),
        )
        await self._session.delete(collection)
        await self._session.commit()
        return True

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> CollectionDocumentPage | None:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        if collection is None:
            return None
        if collection.kind == CollectionKind.MANUAL.value:
            base = (
                select(Document)
                .join(CollectionDocument, CollectionDocument.document_id == Document.id)
                .where(
                    CollectionDocument.collection_id == collection.id,
                    Document.owner_id == owner_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                )
            )
            total = int(
                await self._session.scalar(
                    select(func.count(Document.id))
                    .join(CollectionDocument, CollectionDocument.document_id == Document.id)
                    .where(
                        CollectionDocument.collection_id == collection.id,
                        Document.owner_id == owner_id,
                        Document.status != DocumentStatus.ARCHIVED.value,
                    ),
                )
                or 0
            )
        else:
            rule = DocumentRule.from_mapping(collection.rule)
            base = apply_document_rule(
                select(Document).where(Document.owner_id == owner_id),
                rule,
            )
            total = await self._count_dynamic_documents(owner_id, rule)

        result = await self._session.execute(
            base.order_by(Document.created_at.desc()).limit(limit).offset(offset),
        )
        return CollectionDocumentPage(documents=tuple(result.scalars().unique()), total=total)

    async def add_document(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        collection_id: UUID,
        document_id: UUID,
    ) -> bool | None:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        document = await self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            ),
        )
        if collection is None or document is None:
            return None
        if collection.kind != CollectionKind.MANUAL.value:
            raise InvalidCollectionOperationError(
                "Dynamic collection membership is controlled by its rule"
            )
        if document.status == DocumentStatus.ARCHIVED.value:
            raise InvalidCollectionOperationError(
                "Archived documents cannot be added to collections"
            )
        existing = await self._session.get(
            CollectionDocument,
            {"collection_id": collection_id, "document_id": document_id},
        )
        if existing is not None:
            return False
        self._session.add(
            CollectionDocument(
                collection_id=collection_id,
                document_id=document_id,
                added_by_id=actor_id,
            ),
        )
        self._session.add(
            collection_event(
                owner_id=owner_id,
                actor_id=actor_id,
                document_id=document_id,
                collection=collection,
                action="document_added",
            ),
        )
        await self._session.commit()
        return True

    async def list_membership_candidates(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> CollectionDocumentPage | None:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        if collection is None:
            return None
        if collection.kind != CollectionKind.MANUAL.value:
            raise InvalidCollectionOperationError(
                "Dynamic collection membership is controlled by its rule"
            )
        membership_ids = select(CollectionDocument.document_id).where(
            CollectionDocument.collection_id == collection.id
        )
        base = select(Document).where(
            Document.owner_id == owner_id,
            Document.status != DocumentStatus.ARCHIVED.value,
            Document.id.not_in(membership_ids),
        )
        count = select(func.count(Document.id)).where(
            Document.owner_id == owner_id,
            Document.status != DocumentStatus.ARCHIVED.value,
            Document.id.not_in(membership_ids),
        )
        normalized_query = query.strip()
        if normalized_query:
            query_clause = or_(
                case_insensitive_contains(Document.title, normalized_query),
                case_insensitive_contains(Document.original_filename, normalized_query),
                case_insensitive_contains(Document.issuer, normalized_query),
                case_insensitive_contains(Document.organization, normalized_query),
            )
            base = base.where(query_clause)
            count = count.where(query_clause)
        total = int(await self._session.scalar(count) or 0)
        documents = tuple(
            (
                await self._session.execute(
                    base.order_by(Document.created_at.desc()).limit(limit).offset(offset),
                )
            ).scalars()
        )
        return CollectionDocumentPage(documents=documents, total=total)

    async def remove_document(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        collection_id: UUID,
        document_id: UUID,
    ) -> bool | None:
        collection = await self.get_collection(owner_id=owner_id, collection_id=collection_id)
        if collection is None:
            return None
        if collection.kind != CollectionKind.MANUAL.value:
            raise InvalidCollectionOperationError(
                "Dynamic collection membership is controlled by its rule"
            )
        existing = await self._session.get(
            CollectionDocument,
            {"collection_id": collection_id, "document_id": document_id},
        )
        if existing is None:
            return False
        await self._session.delete(existing)
        self._session.add(
            collection_event(
                owner_id=owner_id,
                actor_id=actor_id,
                document_id=document_id,
                collection=collection,
                action="document_removed",
            ),
        )
        await self._session.commit()
        return True

    async def _count_collection_documents(
        self,
        owner_id: UUID,
        collection: VaultCollection,
    ) -> int:
        if collection.kind == CollectionKind.DYNAMIC.value:
            return await self._count_dynamic_documents(
                owner_id,
                DocumentRule.from_mapping(collection.rule),
            )
        return int(
            await self._session.scalar(
                select(func.count(Document.id))
                .join(CollectionDocument, CollectionDocument.document_id == Document.id)
                .where(
                    CollectionDocument.collection_id == collection.id,
                    Document.owner_id == owner_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                ),
            )
            or 0
        )

    async def _count_dynamic_documents(self, owner_id: UUID, rule: DocumentRule) -> int:
        statement = apply_document_rule(
            select(func.count(Document.id)).where(Document.owner_id == owner_id),
            rule,
        )
        return int(await self._session.scalar(statement) or 0)

    async def _collection_slug_exists(self, owner_id: UUID, slug: str) -> bool:
        return (
            await self._session.scalar(
                select(VaultCollection.id).where(
                    VaultCollection.owner_id == owner_id,
                    VaultCollection.slug == slug,
                ),
            )
            is not None
        )


def validate_collection_rule(kind: CollectionKind, rule: DocumentRule) -> None:
    if kind is CollectionKind.MANUAL:
        return
    if rule.is_empty:
        raise InvalidCollectionOperationError(
            "Dynamic collections require at least one matching condition"
        )
    for document_type in rule.document_types:
        get_document_type(document_type)


def slugify_collection(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "collection"


def normalize_optional(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized[:max_length] or None


def collection_event(
    *,
    owner_id: UUID,
    actor_id: UUID,
    document_id: UUID,
    collection: VaultCollection,
    action: str,
) -> TimelineEvent:
    return TimelineEvent(
        owner_id=owner_id,
        actor_id=actor_id,
        document_id=document_id,
        event_type=TimelineEventType.COLLECTIONS_CHANGED.value,
        payload={
            "action": action,
            "collection_id": str(collection.id),
            "collection": collection.slug,
        },
    )
