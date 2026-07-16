from enum import StrEnum


class TimelineEventType(StrEnum):
    AI_SUMMARY_REGENERATED = "ai_summary_regenerated"
    COLLECTIONS_CHANGED = "collections_changed"
    DOCUMENT_ARCHIVED = "document_archived"
    DOCUMENT_UPLOADED = "document_uploaded"
    METADATA_EDITED = "metadata_edited"
    TAGS_CHANGED = "tags_changed"
    VERSION_CREATED = "version_created"
