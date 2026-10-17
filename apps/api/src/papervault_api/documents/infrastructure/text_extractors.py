import csv
import io
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from papervault_api.core.config import Settings, get_settings
from papervault_api.documents.application.extraction import (
    OcrTextBlock,
    PdfPageAssessment,
    TextExtractionResult,
    TextExtractor,
)
from papervault_api.documents.domain.enums import TextExtractionSource, TextExtractionStatus


class CompositeTextExtractor(TextExtractor):
    def __init__(self, *, pdf_extractor: TextExtractor, ocr_extractor: TextExtractor) -> None:
        self._pdf_extractor = pdf_extractor
        self._ocr_extractor = ocr_extractor

    def extract(self, file_path: Path, content_type: str) -> TextExtractionResult:
        if content_type == "application/pdf":
            result = self._pdf_extractor.extract(file_path, content_type)
            if result.status is TextExtractionStatus.SUCCEEDED:
                assessed_pages = {page.page_number - 1 for page in result.page_assessments}
                required_pages = {
                    page.page_number - 1 for page in result.page_assessments if page.requires_ocr
                } | {
                    index
                    for index, text in enumerate(result.page_texts)
                    if not text.strip() and index not in assessed_pages
                }
                if not required_pages:
                    return result
                ocr_result = self._ocr_extractor.extract(file_path, content_type)
                if ocr_result.status is not TextExtractionStatus.SUCCEEDED:
                    return replace(
                        result,
                        status=TextExtractionStatus.FAILED,
                        error_message=(
                            "PDF pages require OCR to cover missing or image-based content. "
                            + (ocr_result.error_message or "OCR did not produce usable text.")
                        ),
                    )
                if len(ocr_result.page_texts) != len(result.page_texts):
                    return replace(
                        result,
                        status=TextExtractionStatus.FAILED,
                        error_message=(
                            "OCR did not cover every PDF page. Retry with a higher page limit."
                        ),
                    )
                empty_pages = [
                    index + 1
                    for index in sorted(required_pages)
                    if not ocr_result.page_texts[index].strip()
                ]
                if empty_pages:
                    return replace(
                        result,
                        status=TextExtractionStatus.FAILED,
                        error_message=(
                            f"OCR produced no text for required pages {empty_pages}. "
                            "Extraction coverage could not be established."
                        ),
                    )
                footer_only_pages = [
                    index + 1
                    for index in sorted(required_pages)
                    if result.page_texts[index].strip()
                    and sum(char.isalnum() for char in result.page_texts[index]) < 40
                    and merge_page_text(result.page_texts[index], ocr_result.page_texts[index])
                    == result.page_texts[index].strip()
                ]
                if footer_only_pages:
                    return replace(
                        result,
                        status=TextExtractionStatus.FAILED,
                        error_message=(
                            f"OCR only repeated sparse embedded text on pages {footer_only_pages}. "
                            "Image content could not be verified; review the source."
                        ),
                    )
                pages = tuple(
                    merge_page_text(embedded, ocr) if index in required_pages else embedded
                    for index, (embedded, ocr) in enumerate(
                        zip(result.page_texts, ocr_result.page_texts, strict=True)
                    )
                )
                blocks = tuple(
                    ()
                    if index not in required_pages
                    else ocr_result.page_blocks[index]
                    if index < len(ocr_result.page_blocks)
                    else ()
                    for index, embedded in enumerate(result.page_texts)
                )
                return replace(
                    ocr_result,
                    content_text="\n\n".join(pages).strip(),
                    page_texts=pages,
                    page_blocks=blocks,
                    page_count=result.page_count,
                    extractor="pypdf+tesseract_cli",
                    page_assessments=result.page_assessments,
                )
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
            pages: list[str] = []
            assessments: list[PdfPageAssessment] = []
            for page_number, page in enumerate(reader.pages, start=1):
                text, assessment = inspect_pdf_page(page, page_number)
                pages.append(text)
                assessments.append(assessment)
        except Exception as exc:
            return TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.FAILED,
                extractor="pypdf",
                error_message=str(exc),
            )

        page_texts = tuple(page_text.strip() for page_text in pages)
        content_text = "\n\n".join(page_texts).strip()
        if not content_text:
            return TextExtractionResult(
                source=TextExtractionSource.EMBEDDED_TEXT,
                status=TextExtractionStatus.SKIPPED,
                page_count=len(pages),
                extractor="pypdf",
                error_message="No embedded text found; OCR is required",
                page_texts=page_texts,
                page_assessments=tuple(assessments),
            )

        return TextExtractionResult(
            source=TextExtractionSource.EMBEDDED_TEXT,
            status=TextExtractionStatus.SUCCEEDED,
            content_text=content_text,
            page_texts=page_texts,
            page_count=len(pages),
            extractor="pypdf",
            page_assessments=tuple(assessments),
        )


def inspect_pdf_page(page: Any, page_number: int) -> tuple[str, PdfPageAssessment]:
    image_areas: list[float] = []
    painted_content = False
    reference = page.get("/Resources")
    resources = reference.get_object() if reference is not None else {}
    objects = resources.get("/XObject", {})
    if hasattr(objects, "get_object"):
        objects = objects.get_object()
    page_area = float(page.mediabox.width * page.mediabox.height)

    def inspect_image(
        operator: bytes,
        operands: list[Any],
        matrix: list[float],
        text_matrix: list[float],
    ) -> None:
        nonlocal painted_content
        if operator in {
            b"Do",
            b"S",
            b"s",
            b"f",
            b"F",
            b"f*",
            b"B",
            b"B*",
            b"b",
            b"b*",
            b"sh",
            b"INLINE IMAGE",
        }:
            painted_content = True
        if operator != b"Do" or not operands or page_area <= 0:
            return
        reference = objects.get(operands[0])
        if reference is None:
            return
        image = reference.get_object()
        area = abs(matrix[0] * matrix[3] - matrix[1] * matrix[2])
        if image.get("/Subtype") == "/Image":
            image_areas.append(area / page_area)
        elif image.get("/Subtype") == "/Form" and form_contains_images(image):
            # Form XObjects can wrap an entire scanned page. Their unit
            # square is their BBox, unlike raster Image XObjects.
            bounds = image.get("/BBox", [0, 0, 0, 0])
            form_matrix = image.get("/Matrix", [1, 0, 0, 1, 0, 0])
            form_scale = abs(
                float(form_matrix[0] * form_matrix[3] - form_matrix[1] * form_matrix[2])
            )
            image_areas.append(
                area
                * form_scale
                * abs(float(bounds[2] - bounds[0]))
                * abs(float(bounds[3] - bounds[1]))
                / page_area
            )

    text = page.extract_text(visitor_operand_before=inspect_image) or ""
    coverage = round(min(1.0, sum(image_areas)), 4)
    if not text.strip() and not painted_content:
        return text, PdfPageAssessment(page_number, False, coverage, ("blank_page",))
    reasons: list[str] = []
    if not text.strip():
        reasons.append("no_embedded_text")
    if coverage >= 0.2:
        reasons.append("substantial_raster_content")
    elif coverage >= 0.02 and sum(char.isalnum() for char in text) < 40:
        reasons.append("sparse_text_with_raster_content")
    if text and text.count("\ufffd") / len(text) > 0.02:
        reasons.append("damaged_text_encoding")
    return text, PdfPageAssessment(page_number, bool(reasons), coverage, tuple(reasons))


def form_contains_images(form: Any, *, depth: int = 0) -> bool:
    if depth >= 8:
        # Treat excessively nested resources conservatively rather than skipping OCR.
        return True
    resources = form.get("/Resources")
    if resources is None:
        return False
    objects = resources.get_object().get("/XObject", {})
    if hasattr(objects, "get_object"):
        objects = objects.get_object()
    for reference in objects.values():
        child = reference.get_object()
        if child.get("/Subtype") == "/Image" or (
            child.get("/Subtype") == "/Form" and form_contains_images(child, depth=depth + 1)
        ):
            return True
    return False


def merge_page_text(embedded: str, ocr: str) -> str:
    """Preserve native text and append distinct OCR lines."""
    lines = embedded.strip().splitlines()
    known = {" ".join(line.casefold().split()) for line in lines}
    for line in ocr.strip().splitlines():
        normalized = " ".join(line.casefold().split())
        if normalized and normalized not in known:
            lines.append(line)
            known.add(normalized)
    return "\n".join(lines).strip()


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
        if self._max_pdf_pages is not None:
            from pypdf import PdfReader

            try:
                total_pages = len(PdfReader(file_path).pages)
            except Exception:
                return self._failure(
                    "Could not read PDF pages. Check whether the file is encrypted or damaged."
                )
            if total_pages > self._max_pdf_pages:
                return self._failure(
                    f"PDF has {total_pages} pages, exceeding the OCR limit of "
                    f"{self._max_pdf_pages}. Increase PAPERVAULT_OCR_MAX_PDF_PAGES "
                    "or split the document; no pages were silently omitted."
                )
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
        page_blocks: list[tuple[OcrTextBlock, ...]] = []
        confidences: list[float] = []
        for image_path in image_paths:
            args = [
                self._tesseract_command,
                str(image_path),
                "stdout",
                "-l",
                self._languages,
                "--psm",
                str(self._page_segmentation_mode),
                "tsv",
            ]
            result = self._run_command(args)
            if isinstance(result, TextExtractionResult):
                return result
            parsed = parse_tesseract_tsv(result.stdout)
            page_texts.append(parsed.text)
            page_blocks.append(parsed.blocks)
            confidences.extend(
                block.confidence_score
                for block in parsed.blocks
                if block.confidence_score is not None
            )

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
            page_texts=tuple(page_texts),
            page_blocks=tuple(page_blocks),
            page_count=page_count,
            language=self._languages,
            confidence_score=(
                round(sum(confidences) / len(confidences), 4) if confidences else None
            ),
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


@dataclass(frozen=True, slots=True)
class ParsedTesseractPage:
    text: str
    blocks: tuple[OcrTextBlock, ...]


def parse_tesseract_tsv(content: str) -> ParsedTesseractPage:
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    rows = list(reader)
    if not rows or not reader.fieldnames or "level" not in reader.fieldnames:
        return ParsedTesseractPage(text=content.strip(), blocks=())

    page_row = next((row for row in rows if row.get("level") == "1"), None)
    page_width = positive_int(page_row.get("width") if page_row else None)
    page_height = positive_int(page_row.get("height") if page_row else None)
    if page_width is None or page_height is None:
        return ParsedTesseractPage(text="", blocks=())

    blocks: list[OcrTextBlock] = []
    lines: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        left = non_negative_int(row.get("left"))
        top = non_negative_int(row.get("top"))
        width = positive_int(row.get("width"))
        height = positive_int(row.get("height"))
        if left is None or top is None or width is None or height is None:
            continue
        confidence = confidence_ratio(row.get("conf"))
        blocks.append(
            OcrTextBlock(
                text=text[:500],
                left_ratio=bounded_ratio(left / page_width),
                top_ratio=bounded_ratio(top / page_height),
                width_ratio=bounded_ratio(width / page_width, positive=True),
                height_ratio=bounded_ratio(height / page_height, positive=True),
                confidence_score=confidence,
            )
        )
        line_key = (
            row.get("block_num") or "0",
            row.get("par_num") or "0",
            row.get("line_num") or "0",
        )
        lines.setdefault(line_key, []).append(text)

    text = "\n".join(" ".join(words) for words in lines.values()).strip()
    return ParsedTesseractPage(text=text, blocks=tuple(blocks))


def positive_int(value: str | None) -> int | None:
    try:
        parsed = int(value or "")
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def non_negative_int(value: str | None) -> int | None:
    try:
        parsed = int(value or "")
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def confidence_ratio(value: str | None) -> float | None:
    try:
        confidence = float(value or "")
    except ValueError:
        return None
    if confidence < 0:
        return None
    return round(min(1.0, confidence / 100), 4)


def bounded_ratio(value: float, *, positive: bool = False) -> float:
    lower = 0.0000001 if positive else 0.0
    return round(min(1.0, max(lower, value)), 7)
