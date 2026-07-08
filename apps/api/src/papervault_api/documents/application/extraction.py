from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus


@dataclass(frozen=True, slots=True)
class TextExtractionResult:
    source: TextExtractionSource
    status: TextExtractionStatus
    content_text: str | None = None
    page_count: int | None = None
    language: str | None = None
    confidence_score: float | None = None
    extractor: str | None = None
    error_message: str | None = None


class TextExtractor(Protocol):
    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        raise NotImplementedError
