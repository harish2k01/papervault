"""Annotated quality checks, independent of provider-reported confidence."""

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from papervault_api.documents.application.ai import DocumentAIAnalysisResult
from papervault_api.documents.domain.metadata import normalize_document_metadata


@dataclass(frozen=True)
class QualityCheck:
    metric: str
    field: str
    passed: bool
    expected: object
    actual: object


def comparable(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def fact_matches(expected: object, actual: object) -> bool:
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        if isinstance(actual, bool) or actual is None:
            return False
        try:
            # Currency checks are exact to the annotated cent, not binary float epsilon.
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    return type(expected) is type(actual) and comparable(expected) == comparable(actual)


def contains_phrase(text: str, phrase: str) -> bool:
    normalized = " ".join(text.casefold().split())
    return (
        re.search(
            r"(?<!\w)" + re.escape(" ".join(phrase.casefold().split())) + r"(?!\w)", normalized
        )
        is not None
    )


def evaluate_analysis(
    case: dict[str, Any], analysis: DocumentAIAnalysisResult
) -> list[QualityCheck]:
    expected_category = case["expected_category"]
    checks = [
        QualityCheck(
            "classification",
            "category",
            analysis.category == expected_category,
            expected_category,
            analysis.category,
        )
    ]
    normalized = normalize_document_metadata(analysis.category, analysis.extracted_metadata)
    for field, expected in case.get("expected_metadata", {}).items():
        actual = normalized.data.get(field)
        checks.append(
            QualityCheck("metadata", field, fact_matches(expected, actual), expected, actual)
        )
    for index, alternatives in enumerate(case.get("summary_concepts", [])):
        checks.append(
            QualityCheck(
                "summary_coverage",
                str(index),
                any(contains_phrase(analysis.summary, value) for value in alternatives),
                alternatives,
                analysis.summary,
            )
        )
    for phrase in case.get("forbidden_summary_claims", []):
        checks.append(
            QualityCheck(
                "summary_contradiction",
                phrase,
                not contains_phrase(analysis.summary, phrase),
                "absent",
                analysis.summary,
            )
        )
    tags = {
        str(comparable(tag)).replace("_", "-").replace(" ", "-") for tag in analysis.suggested_tags
    }
    for index, alternatives in enumerate(case.get("tag_facets", [])):
        checks.append(
            QualityCheck(
                "tag_coverage",
                str(index),
                bool(tags.intersection(alternatives)),
                alternatives,
                list(analysis.suggested_tags),
            )
        )
    for tag in case.get("unhelpful_tags", []):
        checks.append(
            QualityCheck("tag_noise", tag, tag not in tags, "absent", list(analysis.suggested_tags))
        )
    return checks


def quality_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, int | float]] = {}
    for result in results:
        for check in result["checks"]:
            metric = totals.setdefault(check["metric"], {"passed": 0, "total": 0})
            metric["total"] += 1
            metric["passed"] += int(check["passed"])
    for metric in totals.values():
        metric["rate"] = round(metric["passed"] / metric["total"], 4)
    return {
        "schema_version": 1,
        "passed": bool(results) and all(result["passed"] for result in results),
        "cases_passed": sum(result["passed"] for result in results),
        "cases_total": len(results),
        "metrics": totals,
        "cases": results,
        "limitations": [
            "Summary checks measure annotated phrase coverage and contradictions, "
            "not all factuality.",
            "Only annotated metadata fields and tag facets are scored; "
            "unannotated claims need review.",
            "Synthetic text cases do not measure photographed-document OCR or semantic retrieval.",
        ],
    }


def serialize_checks(checks: list[QualityCheck]) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]
