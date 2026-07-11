from dataclasses import dataclass
from enum import StrEnum


class MetadataFieldType(StrEnum):
    BOOLEAN = "boolean"
    CURRENCY = "currency"
    DATE = "date"
    DECIMAL = "decimal"
    INTEGER = "integer"
    OBJECT_LIST = "object_list"
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
    DocumentTypeDefinition(
        "offer_letter",
        "Offer Letter",
        (
            field("employer", "Employer", MetadataFieldType.STRING, required=True),
            field("position", "Position", MetadataFieldType.STRING),
            field("offer_date", "Offer Date", MetadataFieldType.DATE),
            field("joining_date", "Joining Date", MetadataFieldType.DATE),
            field("annual_compensation", "Annual Compensation", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition(
        "experience_letter",
        "Experience Letter",
        (
            field("employer", "Employer", MetadataFieldType.STRING, required=True),
            field("employee_name", "Employee Name", MetadataFieldType.STRING),
            field("position", "Position", MetadataFieldType.STRING),
            field("start_date", "Start Date", MetadataFieldType.DATE),
            field("end_date", "End Date", MetadataFieldType.DATE),
        ),
    ),
    DocumentTypeDefinition(
        "tax_return",
        "Tax Return",
        (
            field("taxpayer_name", "Taxpayer Name", MetadataFieldType.STRING),
            field("pan", "PAN", MetadataFieldType.STRING, required=True),
            field("assessment_year", "Assessment Year", MetadataFieldType.STRING),
            field("total_income", "Total Income", MetadataFieldType.CURRENCY),
            field("tax_payable", "Tax Payable", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition(
        "form_16",
        "Form 16",
        (
            field("employer", "Employer", MetadataFieldType.STRING, required=True),
            field("employee_name", "Employee Name", MetadataFieldType.STRING),
            field("pan", "PAN", MetadataFieldType.STRING),
            field("financial_year", "Financial Year", MetadataFieldType.STRING),
            field("total_income", "Total Income", MetadataFieldType.CURRENCY),
            field("tax_deducted", "Tax Deducted", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition(
        "bank_statement",
        "Bank Statement",
        (
            field("bank", "Bank", MetadataFieldType.STRING, required=True),
            field("account_last_four", "Account Last Four", MetadataFieldType.STRING),
            field("statement_start", "Statement Start", MetadataFieldType.DATE),
            field("statement_end", "Statement End", MetadataFieldType.DATE),
            field("opening_balance", "Opening Balance", MetadataFieldType.CURRENCY),
            field("closing_balance", "Closing Balance", MetadataFieldType.CURRENCY),
        ),
    ),
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
    DocumentTypeDefinition(
        "investment_statement",
        "Investment Statement",
        (
            field("institution", "Institution", MetadataFieldType.STRING, required=True),
            field("statement_date", "Statement Date", MetadataFieldType.DATE),
            field("account_number", "Account Number", MetadataFieldType.STRING),
            field("total_value", "Total Value", MetadataFieldType.CURRENCY),
            field("holdings", "Holdings", MetadataFieldType.OBJECT_LIST),
        ),
    ),
    DocumentTypeDefinition(
        "mutual_fund_cas",
        "Mutual Fund CAS",
        (
            field("investor_name", "Investor Name", MetadataFieldType.STRING),
            field("pan", "PAN", MetadataFieldType.STRING),
            field("statement_period", "Statement Period", MetadataFieldType.STRING),
            field("registrar", "Registrar", MetadataFieldType.STRING),
            field("total_value", "Total Value", MetadataFieldType.CURRENCY),
            field("folios", "Folios", MetadataFieldType.OBJECT_LIST),
        ),
    ),
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
    DocumentTypeDefinition(
        "medical_report",
        "Medical Report",
        (
            field("provider", "Provider", MetadataFieldType.STRING, required=True),
            field("patient_name", "Patient Name", MetadataFieldType.STRING),
            field("report_date", "Report Date", MetadataFieldType.DATE),
            field("report_type", "Report Type", MetadataFieldType.STRING),
            field("findings", "Findings", MetadataFieldType.OBJECT_LIST),
        ),
    ),
    DocumentTypeDefinition(
        "invoice",
        "Invoice",
        (
            field("vendor", "Vendor", MetadataFieldType.STRING, required=True),
            field("invoice_number", "Invoice Number", MetadataFieldType.STRING),
            field("purchase_date", "Purchase Date", MetadataFieldType.DATE),
            field("warranty", "Warranty", MetadataFieldType.STRING),
            field("total_amount", "Total Amount", MetadataFieldType.CURRENCY),
            field("line_items", "Line Items", MetadataFieldType.OBJECT_LIST),
        ),
    ),
    DocumentTypeDefinition(
        "warranty_document",
        "Warranty Document",
        (
            field("manufacturer", "Manufacturer", MetadataFieldType.STRING),
            field("product", "Product", MetadataFieldType.STRING, required=True),
            field("serial_number", "Serial Number", MetadataFieldType.STRING),
            field("purchase_date", "Purchase Date", MetadataFieldType.DATE),
            field("expiry_date", "Expiry Date", MetadataFieldType.DATE),
        ),
    ),
    DocumentTypeDefinition(
        "receipt",
        "Receipt",
        (
            field("merchant", "Merchant", MetadataFieldType.STRING, required=True),
            field("receipt_number", "Receipt Number", MetadataFieldType.STRING),
            field("purchase_date", "Purchase Date", MetadataFieldType.DATE),
            field("total_amount", "Total Amount", MetadataFieldType.CURRENCY),
            field("payment_method", "Payment Method", MetadataFieldType.STRING),
            field("line_items", "Line Items", MetadataFieldType.OBJECT_LIST),
        ),
    ),
    DocumentTypeDefinition(
        "passport",
        "Passport",
        (
            field("holder_name", "Holder Name", MetadataFieldType.STRING),
            field("passport_number", "Passport Number", MetadataFieldType.STRING, required=True),
            field("nationality", "Nationality", MetadataFieldType.STRING),
            field("issue_date", "Issue Date", MetadataFieldType.DATE),
            field("expiry_date", "Expiry Date", MetadataFieldType.DATE),
        ),
    ),
    DocumentTypeDefinition(
        "driving_license",
        "Driving License",
        (
            field("holder_name", "Holder Name", MetadataFieldType.STRING),
            field("license_number", "License Number", MetadataFieldType.STRING, required=True),
            field("issue_date", "Issue Date", MetadataFieldType.DATE),
            field("expiry_date", "Expiry Date", MetadataFieldType.DATE),
            field("vehicle_classes", "Vehicle Classes", MetadataFieldType.STRING),
        ),
    ),
    DocumentTypeDefinition(
        "pan_card",
        "PAN",
        (
            field("holder_name", "Holder Name", MetadataFieldType.STRING),
            field("pan", "PAN", MetadataFieldType.STRING, required=True),
            field("date_of_birth", "Date of Birth", MetadataFieldType.DATE),
        ),
    ),
    DocumentTypeDefinition(
        "aadhaar",
        "Aadhaar",
        (
            field("holder_name", "Holder Name", MetadataFieldType.STRING),
            field("aadhaar_last_four", "Aadhaar Last Four", MetadataFieldType.STRING),
            field("date_of_birth", "Date of Birth", MetadataFieldType.DATE),
            field("address", "Address", MetadataFieldType.STRING),
        ),
    ),
    DocumentTypeDefinition(
        "property_document",
        "Property Document",
        (
            field("document_kind", "Document Kind", MetadataFieldType.STRING),
            field("property_address", "Property Address", MetadataFieldType.STRING, required=True),
            field("registration_number", "Registration Number", MetadataFieldType.STRING),
            field("registration_date", "Registration Date", MetadataFieldType.DATE),
            field("declared_value", "Declared Value", MetadataFieldType.CURRENCY),
        ),
    ),
    DocumentTypeDefinition(
        "education_certificate",
        "Education Certificate",
        (
            field("institution", "Institution", MetadataFieldType.STRING, required=True),
            field("student_name", "Student Name", MetadataFieldType.STRING),
            field("qualification", "Qualification", MetadataFieldType.STRING),
            field("issue_date", "Issue Date", MetadataFieldType.DATE),
            field("grade", "Grade", MetadataFieldType.STRING),
        ),
    ),
    DocumentTypeDefinition(
        "employment_contract",
        "Employment Contract",
        (
            field("employer", "Employer", MetadataFieldType.STRING, required=True),
            field("employee_name", "Employee Name", MetadataFieldType.STRING),
            field("position", "Position", MetadataFieldType.STRING),
            field("start_date", "Start Date", MetadataFieldType.DATE),
            field("end_date", "End Date", MetadataFieldType.DATE),
            field("annual_compensation", "Annual Compensation", MetadataFieldType.CURRENCY),
        ),
    ),
)

DOCUMENT_TYPE_BY_KEY = {definition.key: definition for definition in DOCUMENT_TYPES}


def get_document_type(document_type: str) -> DocumentTypeDefinition:
    try:
        return DOCUMENT_TYPE_BY_KEY[document_type]
    except KeyError as exc:
        raise UnknownDocumentTypeError(document_type) from exc


def list_document_types() -> tuple[DocumentTypeDefinition, ...]:
    return DOCUMENT_TYPES
