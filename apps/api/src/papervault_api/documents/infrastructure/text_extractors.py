import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from papervault_api.core.config import Settings, get_settings
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


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout_seconds: int) -> CommandResult:
        raise NotImplementedError


class OcrCommandError(RuntimeError):
    pass


class SubprocessCommandRunner(CommandRunner):
    def run(self, args: Sequence[str], *, timeout_seconds: int) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise OcrCommandError(f"OCR command not found: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise OcrCommandError(f"OCR command timed out: {args[0]}") from exc

        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class TesseractCliTextExtractor(TextExtractor):
    def __init__(
        self,
        *,
        tesseract_command: str = "tesseract",
        pdftoppm_command: str = "pdftoppm",
        languages: str = "eng",
        timeout_seconds: int = 120,
        pdf_dpi: int = 200,
        max_pdf_pages: int | None = 50,
        page_segmentation_mode: int = 6,
        runner: CommandRunner | None = None,
    ) -> None:
        self._tesseract_command = tesseract_command
        self._pdftoppm_command = pdftoppm_command
        self._languages = languages
        self._timeout_seconds = timeout_seconds
        self._pdf_dpi = pdf_dpi
        self._max_pdf_pages = max_pdf_pages
        self._page_segmentation_mode = page_segmentation_mode
        self._runner = runner or SubprocessCommandRunner()

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        if content_type in {"image/jpeg", "image/png"}:
            return self._extract_images((file_path,), page_count=1)

        if content_type == "application/pdf":
            return self._extract_pdf(file_path)

        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.FAILED,
            extractor="tesseract_cli",
            error_message=f"Unsupported content type for OCR: {content_type}",
        )

    def _extract_pdf(self, file_path: Path) -> TextExtractionResult:
        with TemporaryDirectory(prefix="papervault-ocr-") as temp_dir:
            output_prefix = Path(temp_dir) / "page"
            args = [
                self._pdftoppm_command,
                "-png",
                "-r",
                str(self._pdf_dpi),
                "-f",
                "1",
            ]
            if self._max_pdf_pages is not None:
                args.extend(["-l", str(self._max_pdf_pages)])
            args.extend([str(file_path), str(output_prefix)])

            rendered = self._run_command(args)
            if isinstance(rendered, TextExtractionResult):
                return rendered

            page_images = sorted(Path(temp_dir).glob("page-*.png"), key=page_sort_key)
            if not page_images:
                return self._failure("PDF rendering produced no page images")
            return self._extract_images(page_images, page_count=len(page_images))

    def _extract_images(
        self,
        image_paths: Sequence[Path],
        *,
        page_count: int,
    ) -> TextExtractionResult:
        page_texts: list[str] = []
        for image_path in image_paths:
            args = [
                self._tesseract_command,
                str(image_path),
                "stdout",
                "-l",
                self._languages,
                "--psm",
                str(self._page_segmentation_mode),
            ]
            result = self._run_command(args)
            if isinstance(result, TextExtractionResult):
                return result
            text = result.stdout.strip()
            if text:
                page_texts.append(text)

        content_text = "\n\n".join(page_texts).strip()
        if not content_text:
            return TextExtractionResult(
                source=TextExtractionSource.OCR,
                status=TextExtractionStatus.SKIPPED,
                page_count=page_count,
                language=self._languages,
                extractor="tesseract_cli",
                error_message="OCR completed but produced no text",
            )

        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.SUCCEEDED,
            content_text=content_text,
            page_count=page_count,
            language=self._languages,
            extractor="tesseract_cli",
        )

    def _run_command(self, args: Sequence[str]) -> CommandResult | TextExtractionResult:
        try:
            result = self._runner.run(args, timeout_seconds=self._timeout_seconds)
        except OcrCommandError as exc:
            return self._failure(str(exc))

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            return self._failure(f"{args[0]} failed with exit code {result.returncode}: {detail}")
        return result

    def _failure(self, error_message: str) -> TextExtractionResult:
        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.FAILED,
            language=self._languages,
            extractor="tesseract_cli",
            error_message=error_message,
        )


class UnavailableOcrTextExtractor(TextExtractor):
    def __init__(self, reason: str | None = None) -> None:
        self._reason = reason

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        return TextExtractionResult(
            source=TextExtractionSource.OCR,
            status=TextExtractionStatus.FAILED,
            extractor="unavailable_ocr",
            error_message=self._reason
            or (
                "OCR provider is not configured. Enable the Tesseract adapter or plug in a "
                "remote OCR adapter behind the TextExtractor interface."
            ),
        )


def build_default_text_extractor(settings: Settings | None = None) -> TextExtractor:
    resolved_settings = settings or get_settings()
    return CompositeTextExtractor(
        pdf_extractor=PypdfTextExtractor(),
        ocr_extractor=build_ocr_text_extractor(resolved_settings),
    )


def build_ocr_text_extractor(settings: Settings) -> TextExtractor:
    provider = settings.ocr_provider.strip().lower()
    if provider == "tesseract":
        return TesseractCliTextExtractor(
            tesseract_command=settings.ocr_tesseract_command,
            pdftoppm_command=settings.ocr_pdftoppm_command,
            languages=settings.ocr_languages,
            timeout_seconds=settings.ocr_timeout_seconds,
            pdf_dpi=settings.ocr_pdf_dpi,
            max_pdf_pages=settings.ocr_max_pdf_pages,
            page_segmentation_mode=settings.ocr_tesseract_psm,
        )

    if provider in {"disabled", "none", "unavailable"}:
        return UnavailableOcrTextExtractor()

    return UnavailableOcrTextExtractor(reason=f"Unknown OCR provider configured: {provider}")


def page_sort_key(path: Path) -> tuple[str, int]:
    stem = path.stem
    prefix, _, number = stem.rpartition("-")
    try:
        page_number = int(number)
    except ValueError:
        page_number = 0
    return prefix, page_number
