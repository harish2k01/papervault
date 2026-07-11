import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus


@dataclass(frozen=True, slots=True)
class OcrTextBlock:
    text: str
    left_ratio: float
    top_ratio: float
    width_ratio: float
    height_ratio: float
    confidence_score: float | None = None


@dataclass(frozen=True, slots=True)
class TextExtractionResult:
    source: TextExtractionSource
    status: TextExtractionStatus
    content_text: str | None = None
    page_texts: tuple[str, ...] = ()
    page_blocks: tuple[tuple[OcrTextBlock, ...], ...] = ()
    page_count: int | None = None
    language: str | None = None
    confidence_score: float | None = None
    extractor: str | None = None
    error_message: str | None = None


class TextExtractor(Protocol):
    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        raise NotImplementedError


def sanitize_extracted_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    return "".join(
        character
        if character in {"\n", "\r", "\t"} or unicodedata.category(character) != "Cc"
        else ""
        for character in normalized
    )
