import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from papervault_api.core.config import Settings
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.identity.application.current_user import CurrentUser
from papervault_api.identity.domain.enums import UserRole
from papervault_api.identity.infrastructure.models import User
from papervault_api.questions.api.routes import (
    ask_question,
    candidate_understanding,
    retry_candidate_understanding,
)
from papervault_api.questions.api.schemas import AskQuestionRequest
from papervault_api.questions.application.evidence_analysis import (
    SourceSpanAnswerProvider,
    extract_findings,
    source_units,
)
from papervault_api.questions.application.hybrid import HybridRetriever
from papervault_api.questions.application.indexing import StructuredIndexingService
from papervault_api.questions.application.service import RetrievedEvidence
from papervault_api.questions.application.structure import split_text, structured_passages
from papervault_api.questions.application.understanding import DocumentUnderstandingService
from papervault_api.questions.infrastructure.local_inference import (
    InferenceUnavailable,
    SemanticModels,
)
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex, DocumentRagPassage


class FakeModels:
    model, revision, dimensions = "fixture-model", "fixture-revision", 2

    def __init__(self) -> None:
        self.seen: list[str] = []

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def rank(self, question: str, texts: list[str]) -> list[tuple[int, float]]:
        self.seen.extend(texts)
        return [
            (index, 0.95 if "Vacation entitlement" in text else 0.001)
            for index, text in enumerate(texts)
        ]


class FakeClient:
    provider, chat_model, embedding_model = "ollama", "fixture", "fixture"

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append(json.loads(user))
        return json.dumps(self.output)

    def embed(self, text: str) -> tuple[float, ...]:
        return (1, 0)

    def health(self) -> tuple[bool, str]:
        return True, "healthy"


async def source(session: AsyncSession, owner: UUID) -> tuple[Document, DocumentTextExtraction]:
    document = Document(
        owner_id=owner,
        title="Synthetic",
        original_filename="synthetic.pdf",
        content_type="application/pdf",
        file_size_bytes=9,
        sha256_hash=hashlib.sha256(b"synthetic").hexdigest(),
        storage_bucket="documents",
        storage_key=str(uuid4()),
        status="ready",
        document_type="generic_pdf",
    )
    session.add(document)
    await session.flush()
    extraction = DocumentTextExtraction(
        document_id=document.id,
        source="embedded_text",
        status="succeeded",
        content_text="Vacation entitlement is twenty days.",
        page_count=1,
        is_current=True,
    )
    session.add(extraction)
    await session.flush()
    session.add(
        DocumentTextPage(
            text_extraction_id=extraction.id,
            page_number=1,
            content_text=extraction.content_text,
        )
    )
    return document, extraction


async def index(
    session: AsyncSession,
    document: Document,
    extraction: DocumentTextExtraction,
    *,
    revision: str = "fixture-revision",
) -> DocumentRagIndex:
    item = DocumentRagIndex(
        document_id=document.id,
        text_extraction_id=extraction.id,
        pipeline_id="fixture",
        parser_model="fixture",
        embedding_model="fixture-model",
        embedding_revision=revision,
        dimensions=2,
        status="ready",
        page_count=1,
        covered_pages=[1],
        warnings=[],
        understanding={},
    )
    session.add(item)
    await session.flush()
    return item


def passage(index_id: UUID, ordinal: int, text: str, vector: list[float]) -> DocumentRagPassage:
    return DocumentRagPassage(
        index_id=index_id,
        ordinal=ordinal,
        page_number=1,
        kind="text",
        section="",
        content_text=text,
        provenance=[{"page_no": 1}],
        vector=vector,
    )


async def test_hybrid_retrieves_zero_overlap_after_5000_and_never_sends_foreign_or_stale_text(
    session: AsyncSession,
) -> None:
    owner, other = User(email="rag@example.test"), User(email="other@example.test")
    session.add_all([owner, other])
    await session.flush()
    document, extraction = await source(session, owner.id)
    current = await index(session, document, extraction)
    session.add_all(
        [
            passage(current.id, ordinal, "Unrelated printer maintenance.", [0, 1])
            for ordinal in range(5001)
        ]
    )
    session.add(passage(current.id, 5001, "Vacation entitlement is twenty days.", [1, 0]))
    session.add(passage(current.id, 5002, "Subject to manager approval.", [0, 1]))
    foreign_doc, foreign_source = await source(session, other.id)
    foreign = await index(session, foreign_doc, foreign_source)
    session.add(passage(foreign.id, 0, "FOREIGN PRIVATE", [1, 0]))
    stale_doc, stale_source = await source(session, owner.id)
    stale_source.is_current = False
    stale = await index(session, stale_doc, stale_source)
    session.add(passage(stale.id, 0, "STALE PRIVATE", [1, 0]))
    incompatible_doc, incompatible_source = await source(session, owner.id)
    incompatible = await index(session, incompatible_doc, incompatible_source, revision="obsolete")
    session.add(passage(incompatible.id, 0, "INCOMPATIBLE PRIVATE", [1, 0]))
    await session.commit()
    models = FakeModels()
    result = await HybridRetriever(session, models, "fixture").retrieve(
        owner.id, "How much paid leave?"
    )
    assert result
    assert result[0].document_id == document.id
    assert "Vacation entitlement" in result[0].content_text
    assert "Subject to manager approval." in result[0].content_text
    assert all("PRIVATE" not in text for text in models.seen)


def test_source_selection_rejects_invented_ids_and_preserves_number_words_and_conditions() -> None:
    text = "Vacation entitlement is twenty working days. Approval is required."
    evidence = (RetrievedEvidence(uuid4(), "Synthetic", "synthetic.pdf", 1, text, 0.9, 0),)
    for output in [
        {"source_ids": [True]},
        {"source_ids": ["E99S0"]},
        {"source_ids": "E0S0"},
        {"source_ids": []},
    ]:
        assert (
            not SourceSpanAnswerProvider(FakeClient(output))
            .answer("How much paid leave?", evidence)
            .answered
        )
    answer = SourceSpanAnswerProvider(FakeClient({"source_ids": ["E0S0", "E0S1", "E0S0"]})).answer(
        "How much paid leave?", evidence
    )
    assert answer.answered
    assert answer.answer == "Vacation entitlement is twenty working days.\nApproval is required."
    assert answer.citations[0].snippet == text and len(answer.citations) == 1
    assert answer.confidence_score == 0


def test_findings_scan_all_passages_without_fixed_document_fields_and_reject_wrong_source() -> None:
    data = [
        {
            "ordinal": i,
            "page_number": i + 1,
            "section": "Terms",
            "text": f"Condition {i}: insurance excludes flooding.",
        }
        for i in range(9)
    ]
    client = FakeClient(
        {
            "findings": [
                {
                    "kind": "exclusion",
                    "label": "Flooding",
                    "source_id": "P8S0",
                },
                {
                    "kind": "amount",
                    "label": "Invented",
                    "source_id": "P999S0",
                },
            ]
        }
    )
    result = extract_findings(client, data)
    assert result["covered_passages"] == 9
    assert {sentence["id"] for call in client.calls for sentence in call["sentences"]} == {
        f"P{i}S0" for i in range(9)
    }
    assert len(result["findings"]) == 1 and result["findings"][0]["page_number"] == 9
    assert result["rejected_findings"] == 2 * len(client.calls) - 1
    assert result["status"] == "needs_review"


def test_structure_retains_reading_order_table_columns_and_page_provenance() -> None:
    data = {
        "body": {
            "children": [{"$ref": "#/texts/0"}, {"$ref": "#/tables/0"}, {"$ref": "#/texts/1"}]
        },
        "texts": [
            {"label": "section_header", "text": "Compensation", "prov": [{"page_no": 2}]},
            {
                "label": "text",
                "text": "Variable compensation is not guaranteed.",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "label": "table",
                "prov": [{"page_no": 2, "bbox": {"l": 10}}],
                "data": {
                    "table_cells": [
                        {"column_header": True, "text": "Component"},
                        {"column_header": True, "text": "Annual INR"},
                        {"start_row_offset_idx": 1, "text": "Base"},
                        {"start_row_offset_idx": 1, "text": "120000"},
                    ]
                },
            }
        ],
    }
    result = structured_passages(data)
    assert [item.kind for item in result] == ["section_header", "table", "text"]
    assert all(item.page == 2 and item.section == "Compensation" for item in result)
    assert "Annual INR" in result[1].text and "Base | 120000" in result[1].text
    assert result[1].provenance[0]["bbox"] == {"l": 10}
    long_text = " ".join(["Unicode résumé and extended clause."] * 90)
    pieces = split_text(long_text)
    assert " ".join(pieces) == long_text
    assert all(len(piece.encode()) <= 700 for piece in pieces)


def test_cross_page_paragraph_uses_character_provenance_and_rejects_overlap() -> None:
    text = "Payment is conditional on " + "verification of the supplied records."
    split = len("Payment is conditional on ")
    data = {
        "body": {"children": [{"$ref": "#/texts/0"}]},
        "texts": [
            {
                "label": "text",
                "text": text,
                "prov": [
                    {"page_no": 1, "charspan": [0, split]},
                    {"page_no": 2, "charspan": [split, len(text)]},
                ],
            }
        ],
    }
    result = structured_passages(data)
    assert [item.page for item in result] == [1, 2]
    assert result[0].text == "Payment is conditional on"
    assert result[1].text == "verification of the supplied records."
    data["texts"][0]["prov"][1]["charspan"] = [0, len(text)]
    with pytest.raises(ValueError, match="overlapping"):
        structured_passages(data)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://169.254.169.254",
        "http://papervault-service.evil.example",
        "http://user:secret@localhost",
    ],
)
def test_private_processing_rejects_public_or_metadata_endpoints(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(rag_parser_url=url)


async def test_index_refuses_incomplete_page_coverage_and_does_not_publish(
    session: AsyncSession,
) -> None:
    owner = User(email="coverage@example.test")
    session.add(owner)
    await session.flush()
    document, extraction = await source(session, owner.id)
    await session.commit()

    class Storage:
        async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
            destination.write_bytes(b"synthetic")

    class Parser:
        identity = "fixture"

        def parse(self, content: bytes, content_type: str) -> dict[str, Any]:
            return {"pages": {"1": {}}, "body": {"children": []}}

    with pytest.raises(InferenceUnavailable, match="coverage"):
        await StructuredIndexingService(
            session, Storage(), Parser(), FakeModels(), "fixture"
        ).build(document.id, extraction.id)
    assert await session.scalar(select(DocumentRagIndex.id)) is None


def test_embedding_identity_and_nan_are_rejected() -> None:
    class Transport:
        def request(self, path: str, payload: Any = None) -> Any:
            return {"model_id": "wrong", "model_sha": "wrong"}

    model = SemanticModels(
        Transport(),
        Transport(),
        model="expected",
        revision="pinned",
        dimensions=2,
        reranker_model="reranker",
        reranker_revision="pinned",
    )
    with pytest.raises(InferenceUnavailable, match="identity"):
        model.embed(["synthetic"])


def test_source_units_preserve_negation_decimals_and_original_number_words() -> None:
    text = "Status: unpaid. Measured value is 13.6 g/dL. Entitlement is twenty days."
    assert source_units(text) == [
        "Status: unpaid.",
        "Measured value is 13.6 g/dL.",
        "Entitlement is twenty days.",
    ]


async def test_candidate_api_checks_owner_and_refuses_incomplete_index(
    session: AsyncSession,
) -> None:
    owner = User(email="api-rag@example.test")
    session.add(owner)
    await session.flush()
    document, _ = await source(session, owner.id)
    await session.commit()
    settings = Settings(rag_mode="preview")
    stranger = CurrentUser(uuid4(), "other@example.test", UserRole.USER)
    with pytest.raises(HTTPException) as denied:
        await candidate_understanding(document.id, stranger, session, settings)
    assert denied.value.status_code == 404
    current = CurrentUser(owner.id, owner.email, UserRole.USER)
    with pytest.raises(HTTPException) as incomplete:
        await ask_question(
            AskQuestionRequest(question="What are my duties?", retrieval="candidate"),
            current,
            session,
            settings,
        )
    assert incomplete.value.status_code == 409


def test_embedding_nan_and_reranker_duplicate_indexes_are_rejected() -> None:
    class Transport:
        def request(self, path: str, payload: Any = None) -> Any:
            if path == "/info":
                return {"model_id": "fixture", "model_sha": "pinned"}
            if path == "/embed":
                return [[float("nan"), 0]]
            return [{"index": 0, "score": 0.8}, {"index": 0, "score": 0.7}]

    model = SemanticModels(
        Transport(),
        Transport(),
        model="fixture",
        revision="pinned",
        dimensions=2,
        reranker_model="fixture",
        reranker_revision="pinned",
    )
    with pytest.raises(InferenceUnavailable, match="values"):
        model.embed(["synthetic"])
    with pytest.raises(InferenceUnavailable, match="duplicate"):
        model.rank("synthetic", ["one", "two"])


class BatchClient(FakeClient):
    def __init__(self, fail_at: int = 0) -> None:
        super().__init__({})
        self.fail_at = fail_at

    def complete(self, *, system: str, user: str) -> str:
        payload = json.loads(user)
        self.calls.append(payload)
        if len(self.calls) == self.fail_at:
            raise RuntimeError("Synthetic interrupted request")
        return json.dumps(
            {
                "findings": [
                    {"kind": "term", "label": "Synthetic term", "source_id": row["id"]}
                    for row in payload["sentences"]
                ]
            }
        )


def batch_passages() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "page_number": 1,
            "section": "Synthetic",
            "text": f"Synthetic clause {ordinal}: " + "word " * 300 + ".",
        }
        for ordinal in range(4)
    ]


def test_findings_resume_only_verified_completed_batches() -> None:
    saved: list[dict[str, Any]] = []
    with pytest.raises(RuntimeError, match="interrupted"):
        extract_findings(BatchClient(fail_at=2), batch_passages(), progress=saved.append)
    assert len(saved) == 1
    client = BatchClient()
    result = extract_findings(client, batch_passages(), checkpoint=saved[0])
    assert result["completed_batches"] == result["total_batches"]
    assert result["covered_passages"] == 4
    assert len(client.calls) == result["total_batches"] - 1
    assert len({finding["source_id"] for finding in result["findings"]}) == 4
    corrupt = {**saved[0], "findings": [{"source_id": []}]}
    fresh = BatchClient()
    extract_findings(fresh, batch_passages(), checkpoint=corrupt)
    assert len(fresh.calls) == result["total_batches"]
    changed = batch_passages()
    changed[0]["text"] = "A replaced source clause."
    replaced = BatchClient()
    updated = extract_findings(replaced, changed, checkpoint=saved[0])
    assert len(replaced.calls) == updated["total_batches"]
    assert updated["batch_plan_id"] != saved[0]["batch_plan_id"]


async def test_understanding_persists_failure_resumes_and_rejects_stale_publications(
    session: AsyncSession,
) -> None:
    owner = User(email="checkpoint@example.test")
    session.add(owner)
    await session.flush()
    document, extraction = await source(session, owner.id)
    item = await index(session, document, extraction)
    session.add_all(
        [passage(item.id, row["ordinal"], row["text"], [1, 0]) for row in batch_passages()]
    )
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    failed = DocumentUnderstandingService(factory, BatchClient(fail_at=2), "fixture", "digest")
    with pytest.raises(RuntimeError):
        await failed.process(item.id)
    await session.refresh(item)
    assert item.understanding["status"] == "failed"
    assert item.understanding["completed_batches"] == 1
    assert item.understanding["findings"]
    old_run = item.understanding["run_id"]
    resumed_client = BatchClient()
    resumed = DocumentUnderstandingService(factory, resumed_client, "fixture", "digest")
    assert await resumed.process(item.id)
    await session.refresh(item)
    assert item.understanding["status"] == "needs_review"
    assert item.understanding["covered_passages"] == 4
    assert len(resumed_client.calls) == item.understanding["total_batches"] - 1
    assert not await resumed.publish(item.id, old_run, {"status": "failed"})
    assert not await resumed.process(item.id)
    new_model = BatchClient()
    assert await DocumentUnderstandingService(factory, new_model, "fixture", "new-digest").process(
        item.id
    )
    assert len(new_model.calls) == item.understanding["total_batches"]
    extraction.is_current = False
    await session.commit()
    assert not await resumed.publish(item.id, item.understanding["run_id"], {"status": "failed"})


async def test_retry_is_owner_guarded_and_routes_ready_index_to_analysis(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from papervault_api.questions.api import routes

    owner = User(email="retry@example.test")
    session.add(owner)
    await session.flush()
    document, extraction = await source(session, owner.id)
    item = await index(session, document, extraction)
    settings = Settings(rag_mode="preview")
    monkeypatch.setattr(routes, "pipeline_id", lambda settings: "fixture")
    sent: list[tuple[str, list[str], str]] = []
    monkeypatch.setattr(
        routes.celery_app,
        "send_task",
        lambda task, *, args, queue: sent.append((task, args, queue)),
    )
    await session.commit()
    stranger = CurrentUser(uuid4(), "other@example.test", UserRole.USER)
    with pytest.raises(HTTPException) as denied:
        await retry_candidate_understanding(document.id, stranger, session, settings)
    assert denied.value.status_code == 404
    current = CurrentUser(owner.id, owner.email, UserRole.USER)
    assert await retry_candidate_understanding(document.id, current, session, settings) == {
        "status": "queued"
    }
    assert sent == [("papervault.rag.understand", [str(item.id)], "papervault-understanding")]
    item.understanding = {"status": "processing"}
    await session.commit()
    with pytest.raises(HTTPException) as busy:
        await retry_candidate_understanding(document.id, current, session, settings)
    assert busy.value.status_code == 409
    assert len(sent) == 1
