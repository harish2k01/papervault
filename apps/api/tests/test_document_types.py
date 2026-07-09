import pytest
from fastapi.testclient import TestClient

from papervault_api.documents.domain.document_types import (
    MetadataFieldType,
    UnknownDocumentTypeError,
    get_document_type,
    list_document_types,
)
from papervault_api.main import create_app


def test_document_type_registry_contains_initial_supported_types() -> None:
    document_type_keys = {definition.key for definition in list_document_types()}

    assert {
        "salary_slip",
        "offer_letter",
        "experience_letter",
        "tax_return",
        "form_16",
        "bank_statement",
        "credit_card_statement",
        "investment_statement",
        "mutual_fund_cas",
        "insurance_policy",
        "medical_report",
        "invoice",
        "warranty_document",
        "receipt",
        "passport",
        "driving_license",
        "pan_card",
        "aadhaar",
        "property_document",
        "education_certificate",
        "employment_contract",
        "generic_pdf",
    }.issubset(document_type_keys)


def test_document_type_registry_has_structured_fields_for_core_examples() -> None:
    salary_slip = get_document_type("salary_slip")
    salary_fields = {field.key: field for field in salary_slip.metadata_fields}

    assert salary_fields["employer"].required is True
    assert salary_fields["net_salary"].field_type is MetadataFieldType.CURRENCY

    credit_card = get_document_type("credit_card_statement")
    credit_card_fields = {field.key: field for field in credit_card.metadata_fields}

    assert credit_card_fields["due_date"].field_type is MetadataFieldType.DATE
    assert credit_card_fields["total_due"].field_type is MetadataFieldType.CURRENCY


def test_unknown_document_type_raises_explicit_error() -> None:
    with pytest.raises(UnknownDocumentTypeError):
        get_document_type("unsupported")


def test_document_type_registry_is_exposed_over_api() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/documents/types")

    assert response.status_code == 200
    body = response.json()
    by_key = {item["key"]: item for item in body}
    assert by_key["salary_slip"]["label"] == "Salary Slip"
    assert any(field["key"] == "net_salary" for field in by_key["salary_slip"]["metadata_fields"])
