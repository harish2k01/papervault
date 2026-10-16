from pathlib import Path

import pytest
from pypdf import PdfWriter

from papervault_api.documents.application.extraction import TextExtractionResult
from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus
from papervault_api.documents.infrastructure.text_extractors import (
    CompositeTextExtractor,
    TesseractCliTextExtractor,
)


class StaticExtractor:
    def __init__(self, result: TextExtractionResult) -> None:
        self.result = result

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        return self.result


def mixed_pdf_extractor(ocr_result: TextExtractionResult) -> CompositeTextExtractor:
    return CompositeTextExtractor(
        pdf_extractor=StaticExtractor(
            TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.SUCCEEDED,
                content_text="Digital cover letter",
                page_texts=("Digital cover letter", ""),
                page_count=2,
            )
        ),
        ocr_extractor=StaticExtractor(ocr_result),
    )


def test_mixed_pdf_preserves_digital_text_and_extracts_scanned_attachment() -> None:
    extractor = mixed_pdf_extractor(
        TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.SUCCEEDED,
            page_texts=("Imperfect OCR of cover letter", "Scanned receipt ZXQ918273"),
            page_count=2,
        )
    )
    result = extractor.extract(Path("mixed.pdf"), "application/pdf")
    assert result.status is TextExtractionStatus.SUCCEEDED
    assert result.page_texts == ("Digital cover letter", "Scanned receipt ZXQ918273")
    assert result.content_text == "Digital cover letter\n\nScanned receipt ZXQ918273"
    assert result.page_count == 2
    assert len(result.page_blocks) == 2


@pytest.mark.parametrize("partial_ocr", [False, True])
def test_mixed_pdf_does_not_report_success_when_ocr_is_missing_or_incomplete(
    partial_ocr: bool,
) -> None:
    extractor = mixed_pdf_extractor(
        TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=(TextExtractionStatus.SUCCEEDED if partial_ocr else TextExtractionStatus.FAILED),
            page_texts=("Cover letter",) if partial_ocr else (),
            error_message=None if partial_ocr else "OCR command not found",
        )
    )
    result = extractor.extract(Path("mixed.pdf"), "application/pdf")
    assert result.status is TextExtractionStatus.FAILED
    assert result.content_text == "Digital cover letter"
    assert result.error_message


def test_ocr_page_limit_is_an_explicit_failure_instead_of_silent_truncation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "too-long.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    writer.write(source)
    result = TesseractCliTextExtractor(max_pdf_pages=2).extract(source, "application/pdf")
    assert result.status is TextExtractionStatus.FAILED
    assert "3 pages" in (result.error_message or "")
    assert "PAPERVAULT_OCR_MAX_PDF_PAGES" in (result.error_message or "")
