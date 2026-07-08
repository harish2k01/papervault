import hashlib
import math
import re
from collections import Counter

from papervault_api.documents.application.ai import (
    DocumentAIAnalysisResult,
    DocumentAIProvider,
    EmbeddingProvider,
    EmbeddingResult,
    ExtractedEntity,
)

WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
AMOUNT_PATTERN = re.compile(r"(?:₹|Rs\.?|INR|\$)\s?[0-9][0-9,]*(?:\.[0-9]{1,2})?", re.I)
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

STOPWORDS = {
    "about",
    "after",
    "amount",
    "and",
    "are",
    "bank",
    "been",
    "being",
    "card",
    "date",
    "document",
    "for",
    "from",
    "has",
    "have",
    "into",
    "invoice",
    "not",
    "number",
    "page",
    "policy",
    "salary",
    "statement",
    "that",
    "the",
    "this",
    "total",
    "with",
    "your",
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "salary_slip": (
        "salary",
        "payslip",
        "pay",
        "earnings",
        "deductions",
        "net salary",
        "gross salary",
        "employer",
    ),
    "credit_card_statement": (
        "credit card",
        "minimum due",
        "total due",
        "payment due",
        "statement period",
    ),
    "bank_statement": ("bank statement", "account number", "debit", "credit", "balance"),
    "insurance_policy": (
        "insurance",
        "policy number",
        "premium",
        "coverage",
        "sum insured",
        "expiry",
    ),
    "invoice": ("invoice", "tax invoice", "bill to", "vendor", "total amount"),
    "warranty_document": ("warranty", "serial number", "expires", "coverage period"),
    "receipt": ("receipt", "paid", "payment", "merchant", "transaction"),
    "medical_report": ("medical", "diagnosis", "patient", "lab", "clinical", "report"),
    "passport": ("passport", "nationality", "place of birth", "date of expiry"),
    "driving_license": ("driving licence", "driving license", "license number"),
    "pan_card": ("permanent account number", "income tax department", "pan"),
    "aadhaar": ("aadhaar", "uidai", "unique identification"),
    "form_16": ("form 16", "tds", "income tax", "assessment year"),
    "tax_return": ("income tax return", "itr", "assessment year", "tax payable"),
    "offer_letter": ("offer letter", "joining date", "compensation", "position"),
    "experience_letter": ("experience letter", "relieving", "employment period"),
    "employment_contract": ("employment agreement", "employment contract", "terms"),
    "investment_statement": ("investment", "portfolio", "holdings", "statement"),
    "mutual_fund_cas": ("consolidated account statement", "mutual fund", "folio"),
    "property_document": ("property", "deed", "sale agreement", "registration"),
    "education_certificate": ("certificate", "university", "degree", "marksheet"),
}

FIELD_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "salary_slip": {
        "employer": ("employer", "company", "organization"),
        "net_salary": ("net salary", "net pay", "net amount"),
        "gross_salary": ("gross salary", "gross pay"),
        "month": ("month", "salary month"),
        "year": ("year", "financial year"),
    },
    "credit_card_statement": {
        "bank": ("bank", "issuer"),
        "statement_period": ("statement period", "period"),
        "due_date": ("due date", "payment due date"),
        "total_due": ("total due", "amount due"),
        "minimum_due": ("minimum due", "minimum amount due"),
    },
    "insurance_policy": {
        "provider": ("provider", "insurer", "insurance company"),
        "policy_number": ("policy number", "policy no"),
        "coverage": ("coverage", "sum insured"),
        "premium": ("premium",),
        "expiry_date": ("expiry date", "valid till", "renewal date"),
    },
    "invoice": {
        "vendor": ("vendor", "seller", "supplier"),
        "invoice_number": ("invoice number", "invoice no"),
        "purchase_date": ("purchase date", "invoice date", "date"),
        "warranty": ("warranty",),
        "total_amount": ("total amount", "grand total", "amount payable"),
    },
}


class LocalDocumentAIProvider(DocumentAIProvider):
    provider = "local"
    model = "rules-v1"

    def analyze(self, text: str, current_document_type: str) -> DocumentAIAnalysisResult:
        category, confidence_score = classify_document(text, current_document_type)
        return DocumentAIAnalysisResult(
            provider=self.provider,
            model=self.model,
            summary=summarize_text(text),
            keywords=extract_keywords(text),
            entities=extract_entities(text),
            suggested_tags=suggest_tags(category, text),
            category=category,
            confidence_score=confidence_score,
            extracted_metadata=extract_metadata(category, text),
        )


class HashingEmbeddingProvider(EmbeddingProvider):
    provider = "local"

    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")
        self._dimensions = dimensions
        self.model = f"hashing-{dimensions}"

    def embed(self, text: str) -> EmbeddingResult:
        vector = [0.0 for _ in range(self._dimensions)]
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [round(value / norm, 8) for value in vector]

        return EmbeddingResult(
            provider=self.provider,
            model=self.model,
            dimensions=self._dimensions,
            vector=tuple(vector),
            vector_norm=round(math.sqrt(sum(value * value for value in vector)), 8),
        )


def build_document_ai_provider(provider: str) -> DocumentAIProvider:
    if provider == "local":
        return LocalDocumentAIProvider()
    raise ValueError(f"Unsupported AI provider: {provider}")


def build_embedding_provider(provider: str, dimensions: int) -> EmbeddingProvider:
    if provider == "local":
        return HashingEmbeddingProvider(dimensions)
    raise ValueError(f"Unsupported embedding provider: {provider}")


def classify_document(text: str, current_document_type: str) -> tuple[str, float]:
    normalized = normalize_text(text)
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword in normalized)

    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score == 0:
        if current_document_type != "generic_pdf":
            return current_document_type, 0.5
        return "generic_pdf", 0.35

    confidence_score = min(0.95, 0.45 + (best_score * 0.12))
    return best_category, round(confidence_score, 4)


def summarize_text(text: str, max_chars: int = 700) -> str:
    sentences = [
        sentence.strip() for sentence in SENTENCE_PATTERN.split(text) if len(sentence.strip()) >= 20
    ]
    if not sentences:
        return text.strip()[:max_chars]
    summary = " ".join(sentences[:3])
    return summary[:max_chars].strip()


def extract_keywords(text: str, limit: int = 12) -> tuple[str, ...]:
    counts = Counter(token for token in tokenize(text) if token not in STOPWORDS)
    return tuple(keyword for keyword, _count in counts.most_common(limit))


def extract_entities(text: str) -> tuple[ExtractedEntity, ...]:
    entities: list[ExtractedEntity] = []
    entities.extend(
        ExtractedEntity("amount", match.group(), 0.7) for match in AMOUNT_PATTERN.finditer(text)
    )
    entities.extend(
        ExtractedEntity("date", match.group(), 0.7) for match in DATE_PATTERN.finditer(text)
    )
    entities.extend(
        ExtractedEntity("email", match.group(), 0.8) for match in EMAIL_PATTERN.finditer(text)
    )
    return tuple(entities[:30])


def suggest_tags(category: str, text: str) -> tuple[str, ...]:
    keyword_tags = tuple(keyword.replace(" ", "-") for keyword in extract_keywords(text, limit=4))
    category_tag = category.replace("_", "-")
    return tuple(dict.fromkeys((category_tag, *keyword_tags)))


def extract_metadata(category: str, text: str) -> dict[str, object]:
    field_patterns = FIELD_PATTERNS.get(category)
    if field_patterns is None:
        return {}

    metadata: dict[str, object] = {}
    for field_name, labels in field_patterns.items():
        value = first_label_value(text, labels)
        if value is None:
            continue
        metadata[field_name] = normalize_metadata_value(field_name, value)
    return metadata


def first_label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}\s*[:#-]\s*([^\n\r]+)", re.I)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def normalize_metadata_value(field_name: str, value: str) -> object:
    if field_name.endswith("_salary") or field_name in {
        "coverage",
        "premium",
        "total_due",
        "minimum_due",
        "total_amount",
    }:
        return parse_amount(value) or value
    if field_name in {"month", "year"}:
        return parse_integer(value) or value
    return value[:255]


def parse_amount(value: str) -> float | None:
    match = re.search(r"[0-9][0-9,]*(?:\.[0-9]{1,2})?", value)
    if match is None:
        return None
    return float(match.group().replace(",", ""))


def parse_integer(value: str) -> int | None:
    match = re.search(r"\d{1,4}", value)
    if match is None:
        return None
    return int(match.group())


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(match.group().lower() for match in WORD_PATTERN.finditer(text))


def normalize_text(text: str) -> str:
    return " ".join(tokenize(text))
