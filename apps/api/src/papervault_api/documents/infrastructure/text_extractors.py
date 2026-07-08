from pathlib import Path

from papervault_api.documents.application.extraction import TextExtractionResult, TextExtractor
from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus


class CompositeTextExtractor(TextExtractor):
    def __init__(self, *, pdf_extractor: TextExtractor, ocr_extractor: TextExtractor) -> None:
        self._pdf_extractor = pdf_extractor
        self._ocr_extractor = ocr_extractor

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        if content_type == "application/pdf":
            result = self._pdf_extractor.extract(file_path, content_type)
            if result.status is TextExtractionStatus.SUCCEEDED:
                return result
            return self._ocr_extractor.extract(file_path, content_type)

        if content_type in {"image/jpeg", "image/png"}:
            return self._ocr_extractor.extract(file_path, content_type)

        return TextExtractionResult(
            source=TextExtractionSource.EMBEDDED_TEXT,
            status=TextExtractionStatus.FAILED,
            extractor="composite",
            error_message=f"Unsupported content type for extraction: {content_type}",
        )


class PypdfTextExtractor(TextExtractor):
    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        if content_type != "application/pdf":
            return TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.SKIPPED,
                extractor="pypdf",
                error_message="Embedded text extraction only supports PDFs",
            )

        try:
            from pypdf import PdfReader

            reader = PdfReader(file_path)
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            return TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.FAILED,
                extractor="pypdf",
                error_message=str(exc),
            )

        content_text = "\n\n".join(page_text.strip() for page_text in pages).strip()
        if not content_text:
            return TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.SKIPPED,
                page_count=len(pages),
                extractor="pypdf",
                error_message="No embedded text found; OCR is required",
            )

        return TextExtractionResult(
            source=TextExtractionSource.EMBEDDED_TEXT,
            status=TextExtractionStatus.SUCCEEDED,
            content_text=content_text,
            page_count=len(pages),
            extractor="pypdf",
        )


class UnavailableOcrTextExtractor(TextExtractor):
    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.FAILED,
            extractor="unavailable_ocr",
            error_message=(
                "OCR provider is not configured. A Tesseract or remote OCR adapter can be "
                "plugged in behind the TextExtractor interface."
            ),
        )


def build_default_text_extractor() -> TextExtractor:
    return CompositeTextExtractor(
        pdf_extractor=PypdfTextExtractor(),
        ocr_extractor=UnavailableOcrTextExtractor(),
    )
