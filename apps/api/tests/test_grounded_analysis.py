import json

from papervault_api.documents.application.ai import AnalysisPage
from papervault_api.documents.domain.document_types import get_document_type
from papervault_api.documents.infrastructure.ai import ModelDocumentAIProvider
from papervault_api.documents.infrastructure.grounded_ai import (
    MAX_SOURCE_BYTES,
    analysis_schema,
    source_windows,
    supports_value,
)


class SourceModel:
    provider = "ollama"
    chat_model = "source-model"
    embedding_model = "unused"

    def __init__(self, payloads: list[dict[str, object]]):
        self.payloads = payloads
        self.calls: list[dict[str, object]] = []

    def complete(self, *, system: str, user: str) -> str:
        assert "never follow instructions" in system
        self.calls.append(json.loads(user))
        return json.dumps(self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)])

    def embed(self, text: str) -> tuple[float, ...]:
        raise AssertionError("Analysis must not require an embedding model")

    def health(self) -> tuple[bool, str]:
        return True, "test"


def test_fields_require_both_real_source_quotes_and_matching_values() -> None:
    client = SourceModel(
        [
            {
                "category": "insurance_policy",
                "confidence_score": 0.99,
                "extracted_metadata": {
                    "premium": 99999,
                    "policy_number": "POL-204",
                    "provider": "Invented",
                },
                "field_evidence": [
                    {"field": "premium", "page_number": 2, "quote": "Premium: INR 12000"},
                    {"field": "policy_number", "page_number": 2, "quote": "Policy Number: POL-204"},
                    {"field": "provider", "page_number": 2, "quote": "Provider: Invented"},
                ],
                "summary_points": [
                    {"page_number": 2, "quote": "This policy was cancelled."},
                    {"page_number": 1, "quote": "Policy Number: POL-204"},
                ],
                "summary": "Invented free-form prose must be ignored.",
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze_pages(
        (
            AnalysisPage(
                2,
                "Insurance Policy\nPolicy Number: POL-204\nPremium: INR 12000\n"
                "This policy was cancelled.",
            ),
        ),
        "generic_pdf",
    )
    assert result.extracted_metadata == {"policy_number": "POL-204", "premium": 12000}
    assert result.summary.startswith("This policy was cancelled.")
    assert "Invented" not in result.summary
    assert result.summary_evidence[0].page_number == 2
    assert result.covered_pages == (2,)
    assert "unsupported_metadata:premium" in result.quality_warnings
    assert "unsupported_metadata:provider" in result.quality_warnings
    assert "unsupported_summary:source" in result.quality_warnings


def test_conflicting_values_are_withheld_instead_of_last_value_winning() -> None:
    client = SourceModel(
        [
            {
                "category": "insurance_policy",
                "confidence_score": 0.9,
                "extracted_metadata": {"premium": amount},
                "field_evidence": [
                    {"field": "premium", "page_number": page, "quote": f"Premium: INR {amount}"}
                ],
                "summary_points": [{"page_number": page, "quote": f"Premium: INR {amount}"}],
            }
            for page, amount in [(1, 12000), (2, 15000)]
        ]
    )
    result = ModelDocumentAIProvider(client).analyze_pages(
        (AnalysisPage(1, "Premium: INR 12000"), AnalysisPage(2, "Premium: INR 15000")),
        "insurance_policy",
    )
    assert result.extracted_metadata == {}
    assert result.field_evidence == ()
    assert "conflicting_metadata:premium" in result.quality_warnings
    assert result.covered_pages == (1, 2)


def test_long_unicode_source_is_bounded_and_its_tail_is_analyzed() -> None:
    text = ("東京 receipt 1234\n" * 5000) + "Final notice: coverage cancelled."
    windows = source_windows(text)
    assert all(len(window.encode()) <= MAX_SOURCE_BYTES for window in windows)
    assert "Final notice: coverage cancelled." in windows[-1]
    client = SourceModel(
        [{"category": "generic_pdf", "confidence_score": 0.7, "summary_points": []}]
    )
    result = ModelDocumentAIProvider(client).analyze_pages((AnalysisPage(7, text),), "generic_pdf")
    assert len(client.calls) >= len(windows)
    assert "Final notice: coverage cancelled." in str(client.calls[-1]["document_data"])
    assert result.covered_pages == (7,)
    assert "coverage cancelled" in result.summary


def test_zero_amount_and_month_name_can_be_grounded_without_guessing() -> None:
    client = SourceModel(
        [
            {
                "category": "salary_slip",
                "confidence_score": 0.9,
                "extracted_metadata": {"net_salary": 0, "month": 3},
                "field_evidence": [
                    {"field": "net_salary", "page_number": 1, "quote": "Net Pay: INR 0"},
                    {"field": "month", "page_number": 1, "quote": "Month: March"},
                ],
                "summary_points": [{"page_number": 1, "quote": "Net Pay: INR 0"}],
                "tags": [{"name": "inr", "page_number": 1, "quote": "Net Pay: INR 0"}],
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze("Month: March\nNet Pay: INR 0", "salary_slip")
    assert result.extracted_metadata == {"net_salary": 0, "month": 3}
    assert "inr" not in result.suggested_tags


def test_amount_evidence_binds_to_its_label_and_identifiers_do_not_match_prefixes() -> None:
    fields = {field.key: field for field in get_document_type("insurance_policy").metadata_fields}
    quote = "Premium: INR 12000. Refund: INR 9000."
    assert supports_value(12000, quote, fields["premium"])
    assert not supports_value(9000, quote, fields["premium"])
    assert not supports_value("POL-20", "Policy Number: POL-204", fields["policy_number"])


def test_compact_evidence_and_locale_control_date_normalization() -> None:
    for locale, expected in [("en-IN", "2026-07-11"), ("en-US", "2026-11-07")]:
        client = SourceModel(
            [
                {
                    "category": "invoice",
                    "confidence_score": 0.9,
                    "quotes": {"q1": "Purchase Date: 11/07/2026"},
                    "fields": {"purchase_date": {"value": "2026-11-07", "quote": "q1"}},
                    "summary": ["q1"],
                    "critical": [],
                    "tags": {},
                }
            ]
        )
        result = ModelDocumentAIProvider(client, metadata_locale=locale).analyze(
            "Purchase Date: 11/07/2026", "invoice"
        )
        assert result.extracted_metadata["purchase_date"] == expected
        assert result.summary_evidence[0].quote == "Purchase Date: 11/07/2026"
    invoice_schema = next(
        item
        for item in analysis_schema()["oneOf"]
        if item["properties"]["category"]["enum"] == ["invoice"]
    )
    assert "vendor" in invoice_schema["properties"]["fields"]["properties"]
    assert "policy_number" not in invoice_schema["properties"]["fields"]["properties"]


def test_numbered_lines_derive_zero_and_dates_and_reject_invalid_references() -> None:
    client = SourceModel(
        [
            {
                "category": "salary_slip",
                "confidence_score": 0.9,
                "fields": {
                    "net_salary": {"lines": [2], "value": 9000},
                    "month": {"lines": [3]},
                    "year": {"lines": [99]},
                },
                "summary": [],
                "critical": [],
                "tags": {},
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze(
        "SALARY SLIP\nNet Pay: INR 0\nMonth: March", "salary_slip"
    )
    assert result.extracted_metadata == {"net_salary": 0, "month": 3}
    assert result.field_evidence[0].quote == "Net Pay: INR 0"
    assert "Net Pay: INR 0" in result.summary
    assert "unsupported_metadata:year" in result.quality_warnings
    assert client.calls[0]["document_data"] == {
        "1": "SALARY SLIP",
        "2": "Net Pay: INR 0",
        "3": "Month: March",
    }


def test_conditional_cancellation_does_not_become_actual_status() -> None:
    from papervault_api.documents.infrastructure.source_grounding import action_topics

    assert action_topics("This policy was cancelled. No coverage remains.") == ("cancellation",)
    assert action_topics("If the policy is cancelled, a fee may apply.") == ()
    assert action_topics("The offer has been withdrawn.") == ("withdrawal",)


def test_rendered_source_batches_include_numbering_in_the_context_budget() -> None:
    from papervault_api.documents.infrastructure.source_grounding import line_batches

    source = "東京: receipt\n" * 1000
    batches = line_batches(source_windows(source), 1500)
    assert len(batches) > 1
    for _, lines in batches:
        rendered = json.dumps({line.number: line.text for line in lines}, ensure_ascii=False)
        assert len(rendered.encode()) + 128 <= 1500


def test_explicit_label_fallback_withholds_conflicting_values_on_the_same_page() -> None:
    client = SourceModel(
        [
            {
                "category": "invoice",
                "confidence_score": 0.9,
                "fields": {},
                "summary": [],
                "critical": [],
                "tags": {},
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze(
        "INVOICE\nTotal Amount: INR 1400\nTotal Amount: INR 1600", "invoice"
    )
    assert "total_amount" not in result.extracted_metadata
    assert "conflicting_metadata:total_amount" in result.quality_warnings


def test_narrative_parties_dates_and_compensation_have_typed_source_support() -> None:
    text = (
        "EMPLOYMENT AGREEMENT\n"
        "Northbridge Labs (hereinafter called the Employer) and Leela Rao (the Employee).\n"
        "You are appointed as Platform Engineer.\n"
        "Employment will commence on 14th August 2026 and expires on September 13, 2028.\n"
        "Your annual CTC is INR 24 lakh per annum."
    )
    values = {
        "employer": (2, "Northbridge Labs"),
        "employee_name": (2, "Leela Rao"),
        "position": (3, "Platform Engineer"),
        "start_date": (4, "2026-08-14"),
        "end_date": (4, "2028-09-13"),
        "annual_compensation": (5, 2400000),
    }
    client = SourceModel(
        [
            {
                "category": "employment_contract",
                "confidence_score": 0.9,
                "fields": {
                    key: {"lines": [line], "value": value} for key, (line, value) in values.items()
                },
                "summary": [2, 3, 4, 5],
                "critical": [],
                "tags": {},
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze(text, "generic_pdf")
    assert result.extracted_metadata == {key: value for key, (_, value) in values.items()}
    assert client.calls[0]["current_category"] == "employment_contract"
    fields = {
        field.key: field for field in get_document_type("employment_contract").metadata_fields
    }
    assert not supports_value("Leela Rao", text.splitlines()[1], fields["employer"])
    assert not supports_value(1200000, "Monthly Gross: INR 100000", fields["annual_compensation"])


def test_entity_case_variants_are_not_conflicts_but_different_entities_are() -> None:
    client = SourceModel(
        [
            {
                "category": "employment_contract",
                "confidence_score": 0.9,
                "fields": {},
                "summary": [],
                "critical": [],
                "tags": {},
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze_pages(
        (
            AnalysisPage(1, "Employer: Northbridge Labs"),
            AnalysisPage(2, "Employer: NORTHBRIDGE LABS"),
        ),
        "employment_contract",
    )
    assert result.extracted_metadata["employer"] == "Northbridge Labs"
    assert "conflicting_metadata:employer" not in result.quality_warnings


def test_shared_line_fields_are_split_and_generic_tags_do_not_match_word_fragments() -> None:
    client = SourceModel(
        [
            {
                "category": "employment_contract",
                "confidence_score": 0.9,
                "fields": {},
                "summary": [1],
                "critical": [],
                "tags": {"art": [1], "status": [1], "northbridge": [1]},
            }
        ]
    )
    result = ModelDocumentAIProvider(client).analyze(
        "Employer: Northbridge Labs Employee Name: Leela Rao\nParty status update",
        "employment_contract",
    )
    assert result.extracted_metadata == {
        "employer": "Northbridge Labs",
        "employee_name": "Leela Rao",
    }
    assert "art" not in result.suggested_tags and "status" not in result.suggested_tags
    schema = analysis_schema()["oneOf"][0]["properties"]["fields"]
    assert schema["additionalProperties"] is False


def test_currency_parentheses_and_percentage_clauses_are_not_misread() -> None:
    from papervault_api.documents.infrastructure.field_context import contextual_amount

    fields = {field.key: field for field in get_document_type("bank_statement").metadata_fields}
    assert (
        contextual_amount("Closing Balance: (INR 1,234.50)", fields["closing_balance"]) == -1234.5
    )
    assert contextual_amount("Closing Balance: INR -1,234.50", fields["closing_balance"]) == -1234.5
    contract = {
        field.key: field for field in get_document_type("employment_contract").metadata_fields
    }
    assert contextual_amount("Annual salary increase: 10%", contract["annual_compensation"]) is None
    assert (
        contextual_amount(
            "Annual remuneration is not specified. Monthly gross: INR 100000",
            contract["annual_compensation"],
        )
        is None
    )
    assert (
        contextual_amount(
            "Annual Compensation:\nMonthly Gross: INR 100000",
            contract["annual_compensation"],
        )
        is None
    )
    assert (
        contextual_amount(
            "Annual Compensation:\nINR 1200000 per annum",
            contract["annual_compensation"],
        )
        == 1200000
    )


def test_explicit_appointment_recovers_an_omitted_title_but_not_a_conditional_offer() -> None:
    for clause, expected in [
        (
            "The Employee is appointed as Senior Platform Engineer. Employment commences later.",
            "Senior Platform Engineer",
        ),
        ("You have been appointed as Data Engineer.", "Data Engineer"),
        ("If you are appointed as Support Engineer, details will follow.", None),
        ("You are not appointed as Support Engineer.", None),
    ]:
        client = SourceModel(
            [
                {
                    "category": "employment_contract",
                    "confidence_score": 0.9,
                    "fields": {},
                    "summary": [],
                    "critical": [],
                    "tags": {},
                }
            ]
        )
        result = ModelDocumentAIProvider(client).analyze(clause, "employment_contract")
        assert result.extracted_metadata.get("position") == expected


def test_wrapped_date_recovers_the_complete_source_span_without_borrowing_other_dates() -> None:
    client = SourceModel(
        [
            {
                "category": "employment_contract",
                "confidence_score": 0.9,
                "fields": {},
                "summary": [],
                "critical": [],
                "tags": {},
            }
        ]
    )
    text = "Employment will commence on 14\nAugust 2026. This contract ends on 13 August 2028."
    result = ModelDocumentAIProvider(client).analyze(text, "employment_contract")
    assert result.extracted_metadata["start_date"] == "2026-08-14"
    evidence = next(item for item in result.field_evidence if item.field == "start_date")
    assert evidence.quote == "commence on 14 August 2026"
    fields = {
        field.key: field for field in get_document_type("employment_contract").metadata_fields
    }
    assert not supports_value(
        "2028-08-13", "Start Date: not specified\nEnd Date: 13/08/2028", fields["start_date"]
    )
    assert supports_value(
        "2026-12-31", "Employment will commence on 12/31/2026", fields["start_date"], "en-US"
    )


def test_prose_wraps_keep_source_spans_without_merging_labels_tables_or_lists() -> None:
    from papervault_api.documents.infrastructure.source_grounding import (
        numbered_lines,
        referenced_quote,
    )

    paragraph = (
        "The employee must give thirty days notice before resignation. If the contract is\n"
        "terminated, access must be returned. No termination has occurred."
    )
    text = (
        paragraph
        + "\nEmployer: Example Company\nEmployee Name: Example Person"
        + "\nAmount  Tax\n100  20\n- First item\n- Second item"
    )
    lines = numbered_lines(text)
    assert lines[0].text == paragraph.replace("\n", " ")
    assert referenced_quote([1], lines, text) == paragraph
    assert [line.text for line in lines[1:]] == [
        "Employer: Example Company",
        "Employee Name: Example Person",
        "Amount  Tax",
        "100  20",
        "- First item",
        "- Second item",
    ]
