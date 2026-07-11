import json
from pathlib import Path
from uuid import uuid4

import pytest

from papervault_api.core.model_clients import JsonHttpResponse
from papervault_api.documents.infrastructure.ai import (
    LocalDocumentAIProvider,
    ModelDocumentAIProvider,
    ModelEmbeddingProvider,
)
from papervault_api.questions.application.service import RetrievedEvidence
from papervault_api.questions.infrastructure.providers import ModelGroundedAnswerProvider


class FakeModelClient:
    provider = "ollama"
    chat_model = "test-chat"
    embedding_model = "test-embedding"

    def __init__(self, response: dict[str, object], vector: tuple[float, ...] = (0.1, 0.2)):
        self._response = response
        self._vector = vector

    def complete(self, *, system: str, user: str) -> str:
        assert system
        assert user
        return json.dumps(self._response)

    def embed(self, text: str) -> tuple[float, ...]:
        return self._vector

    def health(self) -> tuple[bool, str]:
        return True, "healthy"


def test_model_analysis_validates_structured_response() -> None:
    provider = ModelDocumentAIProvider(
        FakeModelClient(
            {
                "summary": "January salary slip with net pay INR 108500.",
                "keywords": ["salary", "net pay"],
                "entities": [{"kind": "amount", "value": "INR 108500"}],
                "suggested_tags": ["salary-slip", "january-2025"],
                "category": "salary_slip",
                "confidence_score": 0.94,
                "extracted_metadata": {"net_salary": 108500},
            }
        )
    )

    result = provider.analyze("Document text", "generic_pdf")

    assert result.category == "salary_slip"
    assert result.confidence_score == 0.94
    assert result.extracted_metadata["net_salary"] == 108500


def test_model_embedding_rejects_dimension_mismatch() -> None:
    provider = ModelEmbeddingProvider(FakeModelClient({}), expected_dimensions=3)

    with pytest.raises(ValueError, match="dimension mismatch"):
        provider.embed("salary")


def test_model_answer_keeps_only_valid_grounded_citations() -> None:
    provider = ModelGroundedAnswerProvider(
        FakeModelClient(
            {
                "answered": True,
                "answer": "The net salary was INR 108500.",
                "confidence_score": 0.91,
                "citation_indexes": [0, 99],
                "refusal_reason": None,
            }
        )
    )
    evidence = (
        RetrievedEvidence(
            document_id=uuid4(),
            title="January Salary Slip",
            original_filename="salary.pdf",
            page_number=1,
            content_text="Net salary INR 108500",
            score=0.9,
            lexical_score=1.0,
        ),
    )

    answer = provider.answer("What was my salary?", evidence)

    assert answer.answered is True
    assert answer.answer == "The net salary was INR 108500."
    assert len(answer.citations) == 1
    assert answer.citations[0].page_number == 1


def test_local_provider_evaluation_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "provider_evaluations.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    provider = LocalDocumentAIProvider()

    for case in cases:
        result = provider.analyze(case["text"], "generic_pdf")
        assert result.category == case["expected_category"], case["name"]
        searchable = " ".join((result.summary, *result.keywords)).lower()
        assert any(term.lower() in searchable for term in case["expected_terms"]), case["name"]
        for field, expected in case.get("expected_metadata", {}).items():
            assert result.extracted_metadata.get(field) == expected, case["name"]


def test_json_http_response_fixture_is_an_object() -> None:
    response = JsonHttpResponse(status_code=200, body={"ok": True})
    assert response.body == {"ok": True}
