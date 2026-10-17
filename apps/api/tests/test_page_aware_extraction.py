from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from papervault_api.documents.application.extraction import TextExtractionResult
from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus
from papervault_api.documents.infrastructure.text_extractors import (
    CompositeTextExtractor,
    PypdfTextExtractor,
)


def create_pdf(
    path: Path,
    *,
    image_size: int = 550,
    form: bool = False,
    text: str = "Scanned by office scanner",
) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    image = DecodedStreamObject()
    image.set_data(b"\xff\xff\xff")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    resource = writer._add_object(image)
    if form:
        wrapper = DecodedStreamObject()
        wrapper.set_data(b"q 550 0 0 550 0 0 cm /Scan Do Q")
        wrapper.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([FloatObject(v) for v in (0, 0, 550, 550)]),
                NameObject("/Resources"): DictionaryObject(
                    {NameObject("/XObject"): DictionaryObject({NameObject("/Scan"): resource})}
                ),
            }
        )
        resource = writer._add_object(wrapper)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                ),
                NameObject("/XObject"): DictionaryObject({NameObject("/Image"): resource}),
            }
        )
    )
    scale = 1 if form else image_size
    stream = DecodedStreamObject()
    stream.set_data(
        (
            f"q {scale} 0 0 {scale} 0 0 cm /Image Do Q\nBT /F1 10 Tf 20 760 Td ({text}) Tj ET"
        ).encode()
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


class RecordingOcr:
    def __init__(
        self, text: str, *, status: TextExtractionStatus = TextExtractionStatus.SUCCEEDED
    ) -> None:
        self.text = text
        self.status = status
        self.called = False

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        self.called = True
        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=self.status,
            content_text=self.text,
            page_texts=(self.text,),
            page_count=1,
        )


@pytest.mark.parametrize("form", [False, True])
def test_scanner_footer_cannot_hide_raster_content(tmp_path: Path, form: bool) -> None:
    source = tmp_path / "scan-with-footer.pdf"
    create_pdf(source, form=form)
    ocr = RecordingOcr("SCANNED RECEIPT\nReference 672839\nScanned by office scanner")
    result = CompositeTextExtractor(pdf_extractor=PypdfTextExtractor(), ocr_extractor=ocr).extract(
        source, "application/pdf"
    )
    assert ocr.called
    assert result.status is TextExtractionStatus.SUCCEEDED
    assert "672839" in (result.content_text or "")
    assert (result.content_text or "").count("Scanned by office scanner") == 1
    assert result.page_assessments[0].requires_ocr
    assert "substantial_raster_content" in result.page_assessments[0].reasons


def test_small_logo_with_real_native_text_does_not_force_ocr(tmp_path: Path) -> None:
    source = tmp_path / "digital-with-logo.pdf"
    text = "Invoice INV-204 from Acme Electronics. Total INR 124999.50. Purchased July 2026."
    create_pdf(source, image_size=50, text=text)
    ocr = RecordingOcr("Incorrect OCR")
    result = CompositeTextExtractor(pdf_extractor=PypdfTextExtractor(), ocr_extractor=ocr).extract(
        source, "application/pdf"
    )
    assert not ocr.called
    assert result.content_text == text
    assert not result.page_assessments[0].requires_ocr


@pytest.mark.parametrize("ocr_text", ["", "Scanned by office scanner"])
def test_missing_raster_text_is_not_reported_as_success(tmp_path: Path, ocr_text: str) -> None:
    source = tmp_path / "incomplete.pdf"
    create_pdf(source)
    ocr = RecordingOcr(ocr_text)
    result = CompositeTextExtractor(pdf_extractor=PypdfTextExtractor(), ocr_extractor=ocr).extract(
        source, "application/pdf"
    )
    assert result.status is TextExtractionStatus.FAILED
    assert result.content_text == "Scanned by office scanner"
    assert result.error_message


def test_required_ocr_failure_preserves_embedded_text_for_inspection(tmp_path: Path) -> None:
    source = tmp_path / "unreadable.pdf"
    create_pdf(source)
    ocr = RecordingOcr("", status=TextExtractionStatus.FAILED)
    result = CompositeTextExtractor(pdf_extractor=PypdfTextExtractor(), ocr_extractor=ocr).extract(
        source, "application/pdf"
    )
    assert result.status is TextExtractionStatus.FAILED
    assert result.content_text == "Scanned by office scanner"
