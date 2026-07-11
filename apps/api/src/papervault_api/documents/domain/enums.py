from enum import StrEnum


class DocumentSourceKind(StrEnum):
    API = "api"
    IMPORT = "import"
    UPLOAD = "upload"


class DocumentStatus(StrEnum):
    ARCHIVED = "archived"
    FAILED = "failed"
    PENDING_PROCESSING = "pending_processing"
    PROCESSING = "processing"
    READY = "ready"
    UPLOADED = "uploaded"


class DocumentReviewStatus(StrEnum):
    APPROVED = "approved"
    NOT_REQUIRED = "not_required"
    PENDING = "pending"


class MetadataSource(StrEnum):
    AI = "ai"
    IMPORT = "import"
    MANUAL = "manual"
    OCR = "ocr"


class AIAnalysisStatus(StrEnum):
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class TextExtractionSource(StrEnum):
    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"


class TextExtractionStatus(StrEnum):
    FAILED = "failed"
    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
