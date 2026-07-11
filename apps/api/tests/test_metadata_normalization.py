from papervault_api.documents.domain.metadata import normalize_document_metadata


def test_invoice_metadata_is_normalized_for_indian_documents() -> None:
    result = normalize_document_metadata(
        "invoice",
        {
            "vendor": "  Apple   India  ",
            "purchase_date": "11/07/2026",
            "total_amount": "INR 1,24,999.50",
            "line_items": [{"description": "iPad", "amount": "124999.50"}],
        },
    )

    assert result.data == {
        "vendor": "Apple India",
        "purchase_date": "2026-07-11",
        "total_amount": 124999.5,
        "line_items": [{"description": "iPad", "amount": "124999.50"}],
    }
    assert result.issues == ()


def test_us_locale_uses_month_first_numeric_dates() -> None:
    result = normalize_document_metadata(
        "credit_card_statement",
        {"bank": "Example Bank", "due_date": "07/11/2026"},
        locale="en-US",
    )

    assert result.data["due_date"] == "2026-07-11"


def test_invalid_and_missing_values_are_reported_for_review() -> None:
    result = normalize_document_metadata(
        "salary_slip",
        {"month": "13", "net_salary": "not available"},
    )

    issue_codes = {(issue.code, issue.field) for issue in result.issues}
    assert ("invalid_value", "month") in issue_codes
    assert ("invalid_value", "net_salary") in issue_codes
    assert ("missing_required", "employer") in issue_codes
