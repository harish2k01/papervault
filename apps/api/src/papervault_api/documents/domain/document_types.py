from dataclasses import dataclass
from enum import StrEnum


class MetadataFieldType(StrEnum):
    BOOLEAN = "boolean"
    CURRENCY = "currency"
    DATE = "date"
    DECIMAL = "decimal"
    INTEGER = "integer"
    STRING = "string"


@dataclass(frozen=True, slots=True)
class MetadataFieldDefinition:
    key: str
    label: str
    field_type: MetadataFieldType
    required: bool = False


@dataclass(frozen=True, slots=True)
class DocumentTypeDefinition:
    key: str
    label: str
    metadata_fields: tuple[MetadataFieldDefinition, ...] = ()


class UnknownDocumentTypeError(ValueError):
    def __init__(self, document_type: str) -> None:
        super().__init__(f"Unknown document type: {document_type}")
        self.document_type = document_type


def field(
    key: str,
    label: str,
    field_type: MetadataFieldType,
    *,
    required: bool = False,
) -> MetadataFieldDefinition:
    return MetadataFieldDefinition(
        key=key,
        label=label,
        field_type=field_type,
        required=required,
    )


DOCUMENT_TYPES: tuple[DocumentTypeDefinition, ...] = (
    DocumentTypeDefinition("generic_pdf", "Generic PDF"),
    DocumentTypeDefinition(
        "salary_slip",
        "Salary Slip",
        (
            field("employer", "Employer", MetadataFieldType.STRING, required=True),
            field("month", "Month", MetadataFieldType.INTEGER, required=True),
            field("year", "Year", MetadataFieldType.INTEGER, required=True),
            field("net_salary", "Net Salary", MetadataFieldType.CURRENCY),
            field("gross_salary", "Gross Salary", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition("offer_letter", "Offer Letter"),
    DocumentTypeDefinition("experience_letter", "Experience Letter"),
    DocumentTypeDefinition("tax_return", "Tax Return"),
    DocumentTypeDefinition("form_16", "Form 16"),
    DocumentTypeDefinition("bank_statement", "Bank Statement"),
    DocumentTypeDefinition(
        "credit_card_statement",
        "Credit Card Statement",
        (
            field("bank", "Bank", MetadataFieldType.STRING, required=True),
            field("statement_period", "Statement Period", MetadataFieldType.STRING),
            field("due_date", "Due Date", MetadataFieldType.DATE),
            field("total_due", "Total Due", MetadataFieldType.CURRENCY),
            field("minimum_due", "Minimum Due", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition("investment_statement", "Investment Statement"),
    DocumentTypeDefinition("mutual_fund_cas", "Mutual Fund CAS"),
    DocumentTypeDefinition(
        "insurance_policy",
        "Insurance Policy",
        (
            field("provider", "Provider", MetadataFieldType.STRING, required=True),
            field("policy_number", "Policy Number", MetadataFieldType.STRING),
            field("coverage", "Coverage", MetadataFieldType.CURRENCY),
            field("premium", "Premium", MetadataFieldType.CURRENCY),
            field("expiry_date", "Expiry Date", MetadataFieldType.DATE),
        ),
    ),
    DocumentTypeDefinition("medical_report", "Medical Report"),
    DocumentTypeDefinition(
        "invoice",
        "Invoice",
        (
            field("vendor", "Vendor", MetadataFieldType.STRING, required=True),
            field("invoice_number", "Invoice Number", MetadataFieldType.STRING),
            field("purchase_date", "Purchase Date", MetadataFieldType.DATE),
            field("warranty", "Warranty", MetadataFieldType.STRING),
            field("total_amount", "Total Amount", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition("warranty_document", "Warranty Document"),
    DocumentTypeDefinition("receipt", "Receipt"),
    DocumentTypeDefinition("passport", "Passport"),
    DocumentTypeDefinition("driving_license", "Driving License"),
    DocumentTypeDefinition("pan_card", "PAN"),
    DocumentTypeDefinition("aadhaar", "Aadhaar"),
    DocumentTypeDefinition("property_document", "Property Document"),
    DocumentTypeDefinition("education_certificate", "Education Certificate"),
    DocumentTypeDefinition("employment_contract", "Employment Contract"),
)

DOCUMENT_TYPE_BY_KEY = {definition.key: definition for definition in DOCUMENT_TYPES}


def get_document_type(document_type: str) -> DocumentTypeDefinition:
    try:
        return DOCUMENT_TYPE_BY_KEY[document_type]
    except KeyError as exc:
        raise UnknownDocumentTypeError(document_type) from exc


def list_document_types() -> tuple[DocumentTypeDefinition, ...]:
    return DOCUMENT_TYPES
