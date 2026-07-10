from collections.abc import Sequence
from pathlib import Path

from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus
from papervault_api.documents.infrastructure.text_extractors import (
    CommandResult,
    OcrCommandError,
    TesseractCliTextExtractor,
)


class FakeOcrCommandRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: Sequence[str], *, timeout_seconds: int) -> CommandResult:
        self.calls.append(list(args))
        command = args[0]
        if command == "pdftoppm":
            output_prefix = Path(args[-1])
            output_prefix.parent.mkdir(parents=True, exist_ok=True)
            Path(f"{output_prefix}-1.png").write_bytes(b"page one")
            Path(f"{output_prefix}-2.png").write_bytes(b"page two")
            return CommandResult(returncode=0, stdout="", stderr="")
        if command == "tesseract":
            return CommandResult(
                returncode=0,
                stdout=f"Text from {Path(args[1]).name}",
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command}")


class MissingCommandRunner:
    def run(self, args: Sequence[str], *, timeout_seconds: int) -> CommandResult:
        raise OcrCommandError(f"OCR command not found: {args[0]}")


def test_tesseract_cli_extractor_reads_image_text(tmp_path: Path) -> None:
    source = tmp_path / "receipt.png"
    source.write_bytes(b"fake image")
    runner = FakeOcrCommandRunner()
    extractor = TesseractCliTextExtractor(
        tesseract_command="tesseract",
        pdftoppm_command="pdftoppm",
        languages="eng",
        runner=runner,
    )

    result = extractor.extract(source, "image/png")

    assert result.source == TextExtractionSource.OCR
    assert result.status == TextExtractionStatus.SUCCEEDED
    assert result.content_text == "Text from receipt.png"
    assert result.page_texts == ("Text from receipt.png",)
    assert result.page_count == 1
    assert runner.calls == [
        ["tesseract", str(source), "stdout", "-l", "eng", "--psm", "6"],
    ]


def test_tesseract_cli_extractor_renders_pdf_pages_before_ocr(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF")
    runner = FakeOcrCommandRunner()
    extractor = TesseractCliTextExtractor(
        tesseract_command="tesseract",
        pdftoppm_command="pdftoppm",
        languages="eng",
        max_pdf_pages=3,
        runner=runner,
    )

    result = extractor.extract(source, "application/pdf")

    assert result.status == TextExtractionStatus.SUCCEEDED
    assert result.page_count == 2
    assert result.content_text == "Text from page-1.png\n\nText from page-2.png"
    assert result.page_texts == ("Text from page-1.png", "Text from page-2.png")
    assert runner.calls[0][:8] == ["pdftoppm", "-png", "-r", "200", "-f", "1", "-l", "3"]
    assert runner.calls[1][0] == "tesseract"
    assert runner.calls[2][0] == "tesseract"


def test_tesseract_cli_extractor_reports_missing_binary(tmp_path: Path) -> None:
    source = tmp_path / "scan.png"
    source.write_bytes(b"fake image")
    extractor = TesseractCliTextExtractor(runner=MissingCommandRunner())

    result = extractor.extract(source, "image/png")

    assert result.status == TextExtractionStatus.FAILED
    assert result.extractor == "tesseract_cli"
    assert result.error_message == "OCR command not found: tesseract"
