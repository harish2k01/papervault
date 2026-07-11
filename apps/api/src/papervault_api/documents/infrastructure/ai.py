import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

from papervault_api.core.config import Settings
from papervault_api.core.model_clients import (
    ModelClient,
    build_model_client,
    parse_json_object,
)
from papervault_api.documents.application.ai import (
    DocumentAIAnalysisResult,
    DocumentAIProvider,
    EmbeddingProvider,
    EmbeddingResult,
    ExtractedEntity,
)
from papervault_api.documents.domain.document_types import (
    UnknownDocumentTypeError,
    get_document_type,
    list_document_types,
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

CATEGORY_STRONG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "salary_slip": ("salary slip", "payslip", "net salary", "net pay", "gross salary"),
    "credit_card_statement": ("credit card statement", "minimum amount due"),
    "bank_statement": ("bank statement", "opening balance", "closing balance"),
    "insurance_policy": ("insurance policy", "policy number", "sum insured"),
    "invoice": ("tax invoice", "invoice number", "bill to"),
    "warranty_document": ("warranty certificate", "warranty document"),
    "receipt": ("payment receipt", "receipt number"),
    "medical_report": ("medical report", "clinical report", "laboratory report"),
    "passport": ("passport number", "republic of india passport"),
    "driving_license": ("driving licence", "driving license"),
    "pan_card": ("permanent account number", "income tax department"),
    "aadhaar": ("unique identification authority", "government of india aadhaar"),
    "form_16": ("form 16", "certificate under section 203"),
    "tax_return": (
        "taxpayer information summary",
        "annual information statement",
        "income tax return",
        "information category processed by system",
    ),
    "offer_letter": ("offer letter", "letter of offer"),
    "experience_letter": ("experience letter", "relieving letter"),
    "employment_contract": ("employment agreement", "employment contract"),
    "investment_statement": ("investment statement", "portfolio statement"),
    "mutual_fund_cas": ("consolidated account statement", "mutual fund cas"),
    "property_document": ("sale deed", "property deed", "sale agreement"),
    "education_certificate": ("degree certificate", "education certificate"),
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
        metadata = extract_metadata(category, text)
        return DocumentAIAnalysisResult(
            provider=self.provider,
            model=self.model,
            summary=summarize_document(category, text, metadata),
            keywords=extract_keywords(text),
            entities=extract_entities(text),
            suggested_tags=suggest_tags(category, text),
            category=category,
            confidence_score=confidence_score,
            extracted_metadata=metadata,
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


class ModelDocumentAIProvider(DocumentAIProvider):
    def __init__(self, client: ModelClient) -> None:
        self._client = client

    def analyze(self, text: str, current_document_type: str) -> DocumentAIAnalysisResult:
        categories = ", ".join(definition.key for definition in list_document_types())
        metadata_schemas = json.dumps(
            {
                definition.key: [field.key for field in definition.metadata_fields]
                for definition in list_document_types()
                if definition.metadata_fields
            },
            separators=(",", ":"),
        )
        payload = parse_json_object(
            self._client.complete(
                system=(
                    "You classify and extract personal documents. Return only JSON with keys: "
                    "summary, keywords, entities, suggested_tags, category, confidence_score, "
                    "extracted_metadata. Every claim must come from the supplied text. "
                    f"category must be one of: {categories}. entities is an array of objects with "
                    "kind, value, and optional confidence_score."
                    f" extracted_metadata must use only the selected category's fields: "
                    f"{metadata_schemas}. Use arrays of objects for table fields."
                ),
                user=(f"Current category: {current_document_type}\nDocument text:\n{text[:50000]}"),
            )
        )
        category = validated_category(payload.get("category"), current_document_type)
        confidence = bounded_float(payload.get("confidence_score"), default=0.5)
        entities = tuple(
            ExtractedEntity(
                kind=str(item.get("kind", "entity"))[:80],
                value=str(item.get("value", ""))[:500],
                confidence_score=bounded_float(
                    item.get("confidence_score"),
                    default=confidence,
                ),
            )
            for item in object_list(payload.get("entities"))[:30]
            if str(item.get("value", "")).strip()
        )
        return DocumentAIAnalysisResult(
            provider=self._client.provider,
            model=self._client.chat_model,
            summary=str(payload.get("summary", "")).strip()[:2000],
            keywords=string_tuple(payload.get("keywords"), limit=20),
            entities=entities,
            suggested_tags=string_tuple(payload.get("suggested_tags"), limit=8),
            category=category,
            confidence_score=confidence,
            extracted_metadata=object_dict(payload.get("extracted_metadata")),
        )


class ModelEmbeddingProvider(EmbeddingProvider):
    def __init__(self, client: ModelClient, expected_dimensions: int) -> None:
        self._client = client
        self._expected_dimensions = expected_dimensions

    def embed(self, text: str) -> EmbeddingResult:
        vector = self._client.embed(text)
        if len(vector) != self._expected_dimensions:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"provider returned {len(vector)}, configured {self._expected_dimensions}"
            )
        norm = math.sqrt(sum(value * value for value in vector))
        return EmbeddingResult(
            provider=self._client.provider,
            model=self._client.embedding_model,
            dimensions=len(vector),
            vector=vector,
            vector_norm=round(norm, 8),
        )


def build_document_ai_provider(
    provider: str,
    settings: Settings | None = None,
) -> DocumentAIProvider:
    if provider == "local":
        return LocalDocumentAIProvider()
    if settings is None:
        raise ValueError(f"Settings are required for AI provider: {provider}")
    if provider in {"ollama", "openai_compatible"}:
        return ModelDocumentAIProvider(build_model_client(provider, settings))
    raise ValueError(f"Unsupported AI provider: {provider}")


def build_embedding_provider(
    provider: str,
    dimensions: int,
    settings: Settings | None = None,
) -> EmbeddingProvider:
    if provider == "local":
        return HashingEmbeddingProvider(dimensions)
    if settings is None:
        raise ValueError(f"Settings are required for embedding provider: {provider}")
    if provider in {"ollama", "openai_compatible"}:
        return ModelEmbeddingProvider(
            build_model_client(provider, settings),
            expected_dimensions=dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


def validated_category(value: Any, fallback: str) -> str:
    candidate = str(value or fallback).strip().lower()
    try:
        get_document_type(candidate)
    except UnknownDocumentTypeError:
        return fallback if fallback else "generic_pdf"
    return candidate


def bounded_float(value: Any, *, default: float) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return default


def string_tuple(value: Any, *, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized = (str(item).strip()[:120] for item in value)
    return tuple(dict.fromkeys(item for item in normalized if item))[:limit]


def object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def object_dict(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key)[:120]: item for key, item in list(value.items())[:50]}


def classify_document(text: str, current_document_type: str) -> tuple[str, float]:
    normalized = normalize_text(text)
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        regular_score = sum(1 for keyword in keywords if keyword in normalized)
        strong_score = sum(
            3 for keyword in CATEGORY_STRONG_KEYWORDS.get(category, ()) if keyword in normalized
        )
        scores[category] = regular_score + strong_score

    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 3:
        if current_document_type != "generic_pdf":
            return current_document_type, 0.5
        return "generic_pdf", 0.4

    runner_up = max(
        (score for category, score in scores.items() if category != best_category), default=0
    )
    margin = max(0, best_score - runner_up)
    confidence_score = min(0.95, 0.55 + (best_score * 0.035) + (margin * 0.015))
    return best_category, round(confidence_score, 4)


def summarize_document(
    category: str,
    text: str,
    metadata: dict[str, object],
    max_chars: int = 700,
) -> str:
    label = category.replace("_", " ").title()
    parts = [f"This document is classified as {label}."]
    if metadata:
        details = "; ".join(
            f"{key.replace('_', ' ')}: {value}"
            for key, value in list(metadata.items())[:6]
            if not isinstance(value, list | dict)
        )
        if details:
            parts.append(f"Extracted details include {details}.")

    entities = extract_entities(text)
    amounts = [entity.value for entity in entities if entity.kind == "amount"][:3]
    dates = [entity.value for entity in entities if entity.kind == "date"][:3]
    if amounts:
        parts.append(f"Detected amounts: {', '.join(amounts)}.")
    if dates:
        parts.append(f"Detected dates: {', '.join(dates)}.")

    if category == "insurance_policy":
        parts.append("Review the policy coverage, premium, and expiry details.")
    elif category in {"invoice", "receipt", "warranty_document"}:
        parts.append("This is a purchase record that may contain payment and warranty details.")
    elif category in {"tax_return", "form_16"}:
        parts.append("This is a tax record containing taxpayer and reported-income information.")
    elif category == "salary_slip":
        parts.append("Review gross earnings, deductions, and net salary for the pay period.")
    elif category == "bank_statement":
        parts.append(
            "Review the account period, transaction activity, and opening and closing balances."
        )

    return " ".join(parts)[:max_chars]


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
    definition = get_document_type(category)
    if not definition.metadata_fields:
        return {}

    metadata: dict[str, object] = {}
    configured_patterns = FIELD_PATTERNS.get(category, {})
    for field_definition in definition.metadata_fields:
        field_name = field_definition.key
        labels = configured_patterns.get(
            field_name,
            (
                field_definition.label,
                field_name.replace("_", " "),
            ),
        )
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
