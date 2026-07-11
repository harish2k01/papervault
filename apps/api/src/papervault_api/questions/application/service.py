import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.ai import EmbeddingProvider
from papervault_api.documents.application.chunking import chunk_page_text
from papervault_api.documents.domain.enums import DocumentStatus, TextExtractionStatus
from papervault_api.documents.infrastructure.ai import tokenize
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextChunk,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.search.application.service import cosine_similarity

MAX_RETRIEVAL_CHUNKS = 5000
MAX_CITATIONS = 5
MIN_LEXICAL_SCORE = 0.34

QUESTION_STOPWORDS = {
    "a",
    "all",
    "an",
    "and",
    "are",
    "did",
    "do",
    "document",
    "documents",
    "every",
    "find",
    "for",
    "from",
    "give",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "show",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
}

CONCEPT_SYNONYMS: dict[str, frozenset[str]] = {
    "salary": frozenset({"salary", "pay", "earnings", "wage", "gross", "net"}),
    "purchase": frozenset({"purchase", "purchased", "invoice", "receipt", "bought"}),
    "insurance": frozenset({"insurance", "policy", "policies", "premium", "insured", "coverage"}),
    "warranty": frozenset({"warranty", "guarantee", "coverage", "expires", "expiry"}),
    "expiry": frozenset(
        {"expiry", "expire", "expires", "expiring", "expiration", "renewal", "valid"}
    ),
    "statement": frozenset({"statement", "statements", "account", "period", "balance"}),
    "august": frozenset({"august", "aug", "08"}),
    "january": frozenset({"january", "jan", "01"}),
    "february": frozenset({"february", "feb", "02"}),
    "march": frozenset({"march", "mar", "03"}),
    "april": frozenset({"april", "apr", "04"}),
    "june": frozenset({"june", "jun", "06"}),
    "july": frozenset({"july", "jul", "07"}),
    "september": frozenset({"september", "sep", "sept", "09"}),
    "october": frozenset({"october", "oct", "10"}),
    "november": frozenset({"november", "nov", "11"}),
    "december": frozenset({"december", "dec", "12"}),
}

CONCEPT_BY_TERM = {term: concept for concept in CONCEPT_SYNONYMS.values() for term in concept}


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    document_id: UUID
    title: str
    original_filename: str
    page_number: int
    content_text: str
    score: float
    lexical_score: float


@dataclass(frozen=True, slots=True)
class QuestionCitation:
    document_id: UUID
    document_title: str
    original_filename: str
    page_number: int
    snippet: str
    relevance_score: float


@dataclass(frozen=True, slots=True)
class QuestionAnswer:
    answered: bool
    answer: str | None
    confidence_score: float
    citations: tuple[QuestionCitation, ...]
    refusal_reason: str | None = None


class GroundedAnswerProvider(Protocol):
    def answer(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> QuestionAnswer:
        raise NotImplementedError


class LocalExtractiveAnswerProvider:
    def answer(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> QuestionAnswer:
        if not evidence or evidence[0].lexical_score < MIN_LEXICAL_SCORE:
            return QuestionAnswer(
                answered=False,
                answer=None,
                confidence_score=0.0,
                citations=(),
                refusal_reason=(
                    "PaperVault could not find enough supporting evidence in your documents."
                ),
            )

        citations = unique_citations(question, evidence)
        primary = citations[0]
        confidence = min(
            0.97,
            0.35 + (evidence[0].lexical_score * 0.45) + (max(evidence[0].score, 0) * 0.2),
        )
        return QuestionAnswer(
            answered=True,
            answer=(
                f'According to "{primary.document_title}" on page '
                f"{primary.page_number}: {primary.snippet}"
            ),
            confidence_score=round(confidence, 4),
            citations=citations,
        )


class QuestionAnsweringService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider,
        answer_provider: GroundedAnswerProvider,
    ) -> None:
        self._session = session
        self._embedding_provider = embedding_provider
        self._answer_provider = answer_provider

    async def ask(self, *, owner_id: UUID, question: str) -> QuestionAnswer:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("Question cannot be empty")

        await self._materialize_missing_chunks(owner_id)
        evidence = await self._retrieve(owner_id, normalized_question)
        return await asyncio.to_thread(
            self._answer_provider.answer,
            normalized_question,
            evidence,
        )

    async def _materialize_missing_chunks(self, owner_id: UUID) -> None:
        result = await self._session.execute(
            select(Document, DocumentTextExtraction)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.document_id == Document.id,
            )
            .where(
                Document.owner_id == owner_id,
                Document.status == DocumentStatus.READY.value,
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == TextExtractionStatus.SUCCEEDED.value,
            )
            .limit(500)
        )
        rows = list(result.all())
        if not rows:
            return

        extraction_ids = [extraction.id for _document, extraction in rows]
        existing_result = await self._session.execute(
            select(DocumentTextChunk.text_extraction_id)
            .where(DocumentTextChunk.text_extraction_id.in_(extraction_ids))
            .distinct()
        )
        existing_ids = set(existing_result.scalars())

        created = False
        for document, extraction in rows:
            if extraction.id in existing_ids:
                continue
            page_result = await self._session.execute(
                select(DocumentTextPage)
                .where(DocumentTextPage.text_extraction_id == extraction.id)
                .order_by(DocumentTextPage.page_number)
            )
            pages = list(page_result.scalars())
            page_texts = (
                [(page.page_number, page.content_text) for page in pages]
                if pages
                else [(1, extraction.content_text or "")]
            )
            for page_number, page_text in page_texts:
                for chunk in chunk_page_text(page_number, page_text):
                    embedding = await asyncio.to_thread(
                        self._embedding_provider.embed,
                        chunk.content_text,
                    )
                    self._session.add(
                        DocumentTextChunk(
                            document_id=document.id,
                            text_extraction_id=extraction.id,
                            page_number=chunk.page_number,
                            chunk_index=chunk.chunk_index,
                            content_text=chunk.content_text,
                            token_count=chunk.token_count,
                            provider=embedding.provider,
                            model=embedding.model,
                            dimensions=embedding.dimensions,
                            vector=list(embedding.vector),
                            vector_norm=embedding.vector_norm,
                            source_text_sha256=hashlib.sha256(
                                chunk.content_text.encode("utf-8")
                            ).hexdigest(),
                        )
                    )
                    created = True
        if created:
            await self._session.commit()

    async def _retrieve(
        self,
        owner_id: UUID,
        question: str,
    ) -> tuple[RetrievedEvidence, ...]:
        query_embedding = (
            await asyncio.to_thread(self._embedding_provider.embed, question)
        ).vector
        concepts = question_concepts(question)
        if not concepts:
            return ()

        result = await self._session.execute(
            select(DocumentTextChunk, Document)
            .join(Document, Document.id == DocumentTextChunk.document_id)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.id == DocumentTextChunk.text_extraction_id,
            )
            .where(
                Document.owner_id == owner_id,
                Document.status == DocumentStatus.READY.value,
                DocumentTextExtraction.is_current.is_(True),
            )
            .limit(MAX_RETRIEVAL_CHUNKS)
        )
        scored: list[RetrievedEvidence] = []
        for chunk, document in result.all():
            searchable_text = (
                f"{document.title} {document.document_type.replace('_', ' ')} {chunk.content_text}"
            )
            lexical = concept_match_score(concepts, searchable_text)
            if lexical == 0:
                continue
            semantic = max(0.0, cosine_similarity(query_embedding, tuple(chunk.vector)))
            score = (lexical * 0.75) + (semantic * 0.25)
            scored.append(
                RetrievedEvidence(
                    document_id=document.id,
                    title=document.title,
                    original_filename=document.original_filename,
                    page_number=chunk.page_number,
                    content_text=chunk.content_text,
                    score=round(score, 6),
                    lexical_score=round(lexical, 6),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return tuple(scored[:MAX_CITATIONS])


def question_concepts(question: str) -> tuple[frozenset[str], ...]:
    concepts: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    question_tokens = tokenize(question)
    for token in question_tokens:
        if token in QUESTION_STOPWORDS:
            continue
        if token == "year" and "this" in question_tokens:
            concept = frozenset({str(datetime.now(UTC).year)})
        else:
            concept = CONCEPT_BY_TERM.get(token, frozenset({token}))
        if concept not in seen:
            concepts.append(concept)
            seen.add(concept)
    return tuple(concepts)


def concept_match_score(concepts: tuple[frozenset[str], ...], text: str) -> float:
    if not concepts:
        return 0.0
    text_tokens = set(tokenize(text))
    matched = sum(1 for concept in concepts if concept.intersection(text_tokens))
    return matched / len(concepts)


def best_excerpt(question: str, text: str, max_chars: int = 320) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    concepts = question_concepts(question)
    candidates = sorted({term for concept in concepts for term in concept}, key=len, reverse=True)
    lower_text = normalized.lower()
    positions = [lower_text.find(term) for term in candidates if lower_text.find(term) >= 0]
    if not positions:
        return normalized[:max_chars].rstrip() + "..."

    best_start = max(0, min(positions) - 80)
    best_score = -1
    for position in positions:
        start = max(0, position - 100)
        window = normalized[start : start + max_chars]
        score = sum(1 for concept in concepts if any(term in window.lower() for term in concept))
        score += min(2, len(re.findall(r"(?:₹|INR|Rs\.?|\$)?\s?\d[\d,]*(?:\.\d+)?", window)))
        if score > best_score:
            best_start = start
            best_score = score
    prefix = "..." if best_start > 0 else ""
    suffix = "..." if best_start + max_chars < len(normalized) else ""
    return f"{prefix}{normalized[best_start : best_start + max_chars].strip()}{suffix}"


def unique_citations(
    question: str,
    evidence: tuple[RetrievedEvidence, ...],
) -> tuple[QuestionCitation, ...]:
    citations: list[QuestionCitation] = []
    seen: set[tuple[UUID, int]] = set()
    for item in evidence:
        key = (item.document_id, item.page_number)
        if key in seen:
            continue
        citations.append(
            QuestionCitation(
                document_id=item.document_id,
                document_title=item.title,
                original_filename=item.original_filename,
                page_number=item.page_number,
                snippet=best_excerpt(question, item.content_text),
                relevance_score=round(item.score, 4),
            )
        )
        seen.add(key)
        if len(citations) >= MAX_CITATIONS:
            break
    return tuple(citations)
