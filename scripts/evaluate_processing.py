"""Run a local processing-quality baseline; failure means annotated expectations were missed."""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from papervault_api.core.config import get_settings
from papervault_api.core.model_clients import JsonHttpClient
from papervault_api.documents.application.evaluation import (
    evaluate_analysis,
    quality_report,
    serialize_checks,
)
from papervault_api.documents.application.ai import (
    AnalysisPage,
    PageAwareDocumentAIProvider,
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
    settings = get_settings()
    provider = build_document_ai_provider(args.provider, settings)
    identity = {}
    if args.provider == "ollama":
        from papervault_api.documents.infrastructure.grounded_ai import PROMPT_VERSION

        http = JsonHttpClient(base_url=settings.ollama_base_url, timeout_seconds=10)
        models = http.request("GET", "/api/tags").body.get("models", [])
        selected = next(
            (item for item in models if item.get("name") == settings.ollama_chat_model),
            None,
        )
        if selected is None:
            parser.error("Configured model is not installed on the local Ollama server")
        identity = {
            "model_manifest_digest": selected["digest"],
            "server_version": http.request("GET", "/api/version").body.get("version"),
            "analysis_contract": PROMPT_VERSION,
            "context_tokens": settings.ollama_context_tokens,
            "max_output_tokens": settings.ollama_max_output_tokens,
        }
    results = []

    def build_report():
        report = quality_report(results)
        report["corpus_complete"] = len(results) == len(cases)
        report["corpus_cases_total"] = len(cases)
        report["passed"] = report["passed"] and report["corpus_complete"]
        report["corpus_sha256"] = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
        report["requested_provider"] = args.provider
        report["inference_identity"] = identity
        return report

    for case in cases:
        started = time.monotonic()
        try:
            if "pages" in case and isinstance(provider, PageAwareDocumentAIProvider):
                analysis = provider.analyze_pages(
                    tuple(
                        AnalysisPage(index + 1, text)
                        for index, text in enumerate(case["pages"])
                    ),
                    case.get("current_category", "generic_pdf"),
                )
            else:
                analysis = provider.analyze(
                    case.get("text", "\n\n".join(case.get("pages", []))),
                    case.get("current_category", "generic_pdf"),
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
                    "latency_seconds": round(time.monotonic() - started, 3),
                    "field_evidence": [
                        asdict(item) for item in analysis.field_evidence
                    ],
                    "summary_evidence": [
                        asdict(item) for item in analysis.summary_evidence
                    ],
                    "quality_warnings": list(analysis.quality_warnings),
                    "covered_pages": list(analysis.covered_pages),
                    "analysis": asdict(analysis),
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
        print(
            f"{case['name']}: {'PASS' if results[-1]['passed'] else 'FAIL'} "
            f"({time.monotonic() - started:.1f}s)",
            file=sys.stderr,
            flush=True,
        )
        failed = [
            f"{item['metric']}:{item['field']}"
            for item in results[-1]["checks"]
            if not item["passed"]
        ]
        if failed:
            print("  Missed: " + ", ".join(failed), file=sys.stderr, flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(build_report(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    report = build_report()
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] or args.report_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
