"""Run synthetic layout/retrieval/answer checks against private candidate services.

Run inside the cluster, or use loopback port forwards. This script only reads the
explicit synthetic fixture; it never connects to the production document database.
"""

import argparse
import json
import textwrap
import time
from pathlib import Path
from uuid import uuid4

from papervault_api.core.config import Settings
from papervault_api.core.model_clients import build_model_client
from papervault_api.questions.application.evidence_analysis import (
    SourceSpanAnswerProvider,
)
from papervault_api.questions.application.service import RetrievedEvidence
from papervault_api.questions.application.structure import structured_passages
from papervault_api.questions.infrastructure.local_inference import (
    LayoutParser,
    PrivateInference,
)
from papervault_api.questions.infrastructure.rag_factory import semantic_models


def synthetic_pdf(text: str) -> bytes:
    lines = [
        line for paragraph in text.splitlines() for line in textwrap.wrap(paragraph, 85)
    ]

    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = (
        "BT /F1 11 Tf 50 740 Td 22 TL "
        + " ".join("(" + escape(line) + ") Tj T*" for line in lines)
        + " ET"
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 6\n0000000000 65535 f \n"
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--answer-model")
    parser.add_argument("--answer-digest")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings()
    settings.validate_private_inference_url(settings.ollama_base_url)
    data = json.loads(args.fixture.read_text())
    layout = LayoutParser(PrivateInference(settings.rag_parser_url, 1200))
    models = semantic_models(settings)
    passages = []
    started = time.monotonic()
    for document in data["documents"]:
        parsed = layout.parse(synthetic_pdf(document["text"]), "application/pdf")
        structured = structured_passages(parsed)
        if len(parsed["pages"]) != 1 or not structured:
            raise AssertionError("Synthetic parser coverage failure")
        for passage in structured:
            passages.append((document["id"], passage))
        print(
            json.dumps({"parsed_family": document["id"], "passages": len(structured)}),
            flush=True,
        )
    vectors = []
    texts = [passage.section + "\n" + passage.text for _, passage in passages]
    for start in range(0, len(texts), 16):
        vectors.extend(models.embed(texts[start : start + 16]))
    answerer = None
    if args.answer_model:
        if not args.answer_digest:
            raise ValueError("A pinned answer model digest is required")
        settings.ollama_chat_model = args.answer_model
        settings.ollama_expected_digest = args.answer_digest
        answerer = SourceSpanAnswerProvider(build_model_client("ollama", settings))
    results = []
    cases = [
        (doc["id"], question, expected)
        for doc in data["documents"]
        for question, expected in doc["questions"]
    ]
    cases += [(None, question, None) for question in data["unanswerable"]]
    for family, question, expected in cases:
        case_started = time.monotonic()
        query_vector = models.embed([question], query=True)[0]
        semantic = sorted(
            range(len(passages)),
            key=lambda index: sum(
                a * b for a, b in zip(query_vector, vectors[index], strict=True)
            ),
            reverse=True,
        )[:16]
        ranked = models.rank(question, [texts[index] for index in semantic])
        top = [(semantic[index], score) for index, score in ranked[:3]]
        row = {
            "family": family,
            "question": question,
            "top_family": passages[top[0][0]][0],
            "top_score": round(top[0][1], 6),
            "retrieval_correct": family is not None
            and passages[top[0][0]][0] == family,
            "expected_span_retrieved": expected is not None
            and any(expected in texts[index] for index, _ in top),
        }
        if answerer:
            evidence = tuple(
                RetrievedEvidence(
                    uuid4(),
                    passages[index][0],
                    "synthetic.pdf",
                    passages[index][1].page,
                    texts[index],
                    score,
                    0,
                )
                for index, score in top
            )
            answer = answerer.answer(question, evidence)
            row["answered"] = answer.answered
            row["answer"] = answer.answer
            row["answer_correct"] = (
                bool(
                    answer.answer
                    and expected
                    and expected.casefold() in answer.answer.casefold()
                )
                if family
                else not answer.answered
            )
            by_document = {item.document_id: item for item in evidence}
            row["source_verified"] = (
                all(
                    citation.document_id in by_document
                    and citation.snippet
                    in by_document[citation.document_id].content_text
                    for citation in answer.citations
                )
                if answer.answered
                else None
            )
            row["refusal_reason"] = answer.refusal_reason
        row["elapsed_seconds"] = round(time.monotonic() - case_started, 2)
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {
        "synthetic_only": True,
        "families": len(data["documents"]),
        "passages": len(passages),
        "embedding_model": models.model,
        "embedding_revision": models.revision,
        "reranker_model": models.reranker_model,
        "reranker_revision": models.reranker_revision,
        "answer_model": args.answer_model,
        "answer_protocol": SourceSpanAnswerProvider.version,
        "answer_digest": args.answer_digest,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "results": results,
        "limitation": "Synthetic text PDFs, not a representative private-document accuracy measurement. Retrieval scores are not calibrated truth probabilities.",
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "positive_top1": sum(row["retrieval_correct"] for row in results),
                "positive_cases": len(cases) - len(data["unanswerable"]),
                "elapsed_seconds": report["elapsed_seconds"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
