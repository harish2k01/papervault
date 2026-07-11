from typing import Any

from papervault_api.core.config import Settings
from papervault_api.core.model_clients import ModelClient, build_model_client, parse_json_object
from papervault_api.questions.application.service import (
    GroundedAnswerProvider,
    LocalExtractiveAnswerProvider,
    QuestionAnswer,
    RetrievedEvidence,
    unique_citations,
)


class ModelGroundedAnswerProvider(GroundedAnswerProvider):
    def __init__(self, client: ModelClient) -> None:
        self._client = client

    def answer(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> QuestionAnswer:
        if not evidence:
            return refused_answer()
        evidence_text = "\n\n".join(
            f"[{index}] {item.title}, page {item.page_number}\n{item.content_text[:2500]}"
            for index, item in enumerate(evidence)
        )
        payload = parse_json_object(
            self._client.complete(
                system=(
                    "Answer only from the numbered evidence. Return JSON with answered, answer, "
                    "confidence_score, citation_indexes, and refusal_reason. Refuse when evidence "
                    "does not support the answer. citation_indexes must refer to supplied evidence."
                ),
                user=f"Question: {question}\n\nEvidence:\n{evidence_text}",
            )
        )
        if payload.get("answered") is not True:
            return refused_answer(str(payload.get("refusal_reason") or ""))

        indexes = valid_indexes(payload.get("citation_indexes"), len(evidence))
        answer_text = str(payload.get("answer") or "").strip()
        if not indexes or not answer_text:
            return refused_answer()

        selected = tuple(evidence[index] for index in indexes)
        citations = unique_citations(question, selected)
        confidence = bounded_confidence(payload.get("confidence_score"))
        return QuestionAnswer(
            answered=True,
            answer=answer_text[:4000],
            confidence_score=confidence,
            citations=citations,
        )


def build_grounded_answer_provider(
    provider: str,
    settings: Settings,
) -> GroundedAnswerProvider:
    if provider == "local":
        return LocalExtractiveAnswerProvider()
    if provider in {"ollama", "openai_compatible"}:
        return ModelGroundedAnswerProvider(build_model_client(provider, settings))
    raise ValueError(f"Unsupported answer provider: {provider}")


def refused_answer(reason: str = "") -> QuestionAnswer:
    return QuestionAnswer(
        answered=False,
        answer=None,
        confidence_score=0.0,
        citations=(),
        refusal_reason=(
            reason.strip()[:1000]
            or "PaperVault could not find enough supporting evidence in your documents."
        ),
    )


def valid_indexes(value: Any, evidence_count: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    indexes: list[int] = []
    for item in value:
        if isinstance(item, int) and 0 <= item < evidence_count and item not in indexes:
            indexes.append(item)
    return tuple(indexes[:5])


def bounded_confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.5
