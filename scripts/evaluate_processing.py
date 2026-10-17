"""Run a local processing-quality baseline; failure means annotated expectations were missed."""

import argparse
import hashlib
import json
from pathlib import Path

from papervault_api.core.config import get_settings
from papervault_api.documents.application.evaluation import (
    evaluate_analysis,
    quality_report,
    serialize_checks,
)
from papervault_api.documents.infrastructure.ai import build_document_ai_provider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("local", "ollama"), default="local")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "apps/api/tests/fixtures/processing_quality.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Return success after writing a report even when quality checks fail.",
    )
    args = parser.parse_args()
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        parser.error("The corpus must be a nonempty array of annotated cases")
    provider = build_document_ai_provider(args.provider, get_settings())
    results = []
    for case in cases:
        try:
            analysis = provider.analyze(
                case["text"], case.get("current_category", "generic_pdf")
            )
            checks = evaluate_analysis(case, analysis)
            results.append(
                {
                    "name": case["name"],
                    "passed": all(check.passed for check in checks),
                    "provider": analysis.provider,
                    "model": analysis.model,
                    "classification_confidence": analysis.confidence_score,
                    "checks": serialize_checks(checks),
                }
            )
        except Exception as error:
            results.append(
                {
                    "name": case["name"],
                    "passed": False,
                    "error_type": type(error).__name__,
                    "checks": [],
                }
            )
    report = quality_report(results)
    report["corpus_sha256"] = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    report["requested_provider"] = args.provider
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] or args.report_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
