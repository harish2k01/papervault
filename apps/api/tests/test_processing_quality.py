from dataclasses import replace

from papervault_api.documents.application.evaluation import (
    contains_phrase,
    evaluate_analysis,
    fact_matches,
    quality_report,
    serialize_checks,
)
from papervault_api.documents.infrastructure.ai import LocalDocumentAIProvider


def test_confident_classification_does_not_mask_missing_facts_or_summary_omissions() -> None:
    analysis = LocalDocumentAIProvider().analyze(
        "Insurance policy number premium coverage", "generic_pdf"
    )
    analysis = replace(analysis, confidence_score=0.99)
    checks = evaluate_analysis(
        {
            "expected_category": "insurance_policy",
            "expected_metadata": {"policy_number": "POL-204"},
            "summary_concepts": [["cancelled", "canceled"]],
        },
        analysis,
    )
    report = quality_report(
        [{"passed": all(check.passed for check in checks), "checks": serialize_checks(checks)}]
    )
    assert report["passed"] is False
    assert report["metrics"]["classification"]["rate"] == 1
    assert report["metrics"]["metadata"]["rate"] == 0
    assert report["metrics"]["summary_coverage"]["rate"] == 0


def test_numeric_facts_do_not_accept_boolean_missing_or_nearly_correct_values() -> None:
    assert fact_matches(0, 0.0)
    assert not fact_matches(0, None)
    assert not fact_matches(1, True)
    assert not fact_matches(124999.50, 124999.49)


def test_summary_phrase_checks_do_not_match_inside_other_words() -> None:
    assert contains_phrase("Policy was CANCELLED. No\ncoverage remains.", "no coverage")
    assert not contains_phrase("Policy remains uncancelled.", "cancelled")


def test_empty_benchmark_and_provider_errors_cannot_pass() -> None:
    assert quality_report([])["passed"] is False
    assert (
        quality_report([{"passed": False, "checks": [], "error_type": "TimeoutError"}])["passed"]
        is False
    )
