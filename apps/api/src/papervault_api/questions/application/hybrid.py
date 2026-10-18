"""Owner-scoped BM25 + semantic RRF candidates followed by learned reranking."""

import asyncio
import heapq
import math
import re
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.questions.application.service import RetrievedEvidence
from papervault_api.questions.infrastructure.local_inference import SemanticModels
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex, DocumentRagPassage


def terms(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


@dataclass(frozen=True)
class Candidate:
    passage: DocumentRagPassage
    document: Document


class HybridRetriever:
    def __init__(
        self,
        session: AsyncSession,
        models: SemanticModels,
        pipeline: str,
        minimum_score: float = 0.0,
    ) -> None:
        self.session = session
        self.models = models
        self.pipeline = pipeline
        self.minimum_score = minimum_score

    def query(self, owner_id: UUID) -> Select[tuple[DocumentRagPassage, Document]]:
        return (
            select(DocumentRagPassage, Document)
            .join(
                DocumentRagIndex,
                DocumentRagPassage.index_id == DocumentRagIndex.id,
            )
            .join(Document, Document.id == DocumentRagIndex.document_id)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.id == DocumentRagIndex.text_extraction_id,
            )
            .where(
                Document.owner_id == owner_id,
                Document.status == "ready",
                Document.archived_at.is_(None),
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == "succeeded",
                DocumentRagIndex.status == "ready",
                DocumentRagIndex.pipeline_id == self.pipeline,
                DocumentRagIndex.embedding_model == self.models.model,
                DocumentRagIndex.embedding_revision == self.models.revision,
                DocumentRagIndex.dimensions == self.models.dimensions,
            )
            .execution_options(yield_per=256)
        )

    async def retrieve(self, owner_id: UUID, question: str) -> tuple[RetrievedEvidence, ...]:
        query_terms = set(terms(question))
        frequencies: Counter[str] = Counter()
        count, length = 0, 0
        # Complete owner corpus, streamed twice with bounded candidate heaps. No first-N
        # cutoff, synchronous index construction or lexical-overlap gate at query time.
        rows = await self.session.stream(self.query(owner_id))
        async for passage, _document in rows:
            page_tokens = terms(passage.section + " " + passage.content_text)
            count += 1
            length += len(page_tokens)
            frequencies.update(query_terms & set(page_tokens))
        if not count:
            return ()
        vector = (await asyncio.to_thread(self.models.embed, [question], query=True))[0]
        average_length = max(1, length / count)
        lexical: list[tuple[float, str, Candidate]] = []
        semantic: list[tuple[float, str, Candidate]] = []
        rows = await self.session.stream(self.query(owner_id))
        async for passage, document in rows:
            candidate = Candidate(passage, document)
            tokens = Counter(terms(passage.section + " " + passage.content_text))
            size = sum(tokens.values())
            bm25 = sum(
                math.log(1 + (count - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                * tokens[term]
                * 2.2
                / (tokens[term] + 1.2 * (0.25 + 0.75 * size / average_length))
                for term in query_terms
                if tokens[term]
            )
            if len(passage.vector) != len(vector) or any(
                not math.isfinite(x) for x in passage.vector
            ):
                continue
            similarity = sum(a * b for a, b in zip(passage.vector, vector, strict=True))
            for heap, score in ((lexical, bm25), (semantic, similarity)):
                if heap is lexical and score <= 0:
                    continue
                entry = (score, str(passage.id), candidate)
                if len(heap) < 40:
                    heapq.heappush(heap, entry)
                elif entry[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, entry)
        fused: dict[str, float] = {}
        candidates: dict[str, Candidate] = {}
        for heap in (lexical, semantic):
            for rank, (_score, identity, candidate) in enumerate(
                sorted(heap, key=lambda row: row[:2], reverse=True), 1
            ):
                fused[identity] = fused.get(identity, 0) + 1 / (60 + rank)
                candidates[identity] = candidate
        shortlist = [
            candidates[key] for key in sorted(fused, key=lambda key: fused[key], reverse=True)[:32]
        ]
        scores: list[tuple[int, float]] = []
        for start in range(0, len(shortlist), 16):
            batch = shortlist[start : start + 16]
            ranked = await asyncio.to_thread(
                self.models.rank,
                question,
                [item.passage.section + "\n" + item.passage.content_text for item in batch],
            )
            scores.extend((start + index, score) for index, score in ranked)
        evidence: list[RetrievedEvidence] = []
        for index, score in sorted(scores, key=lambda item: item[1], reverse=True):
            if score < self.minimum_score:
                continue
            candidate = shortlist[index]
            passage, document = candidate.passage, candidate.document
            # Recheck ownership/current source while expanding adjacent context. A
            # neighbour can never come from a different user or source version. Each
            # page retains its own citation, including clauses continuing across pages.
            neighbors = await self.session.execute(
                self.query(owner_id)
                .where(
                    DocumentRagPassage.index_id == passage.index_id,
                    DocumentRagPassage.ordinal.between(passage.ordinal - 1, passage.ordinal + 1),
                )
                .order_by(DocumentRagPassage.ordinal)
                .execution_options(yield_per=None)
            )
            context = [row[0] for row in neighbors]
            if not any(item.id == passage.id for item in context):
                continue
            source_id = await self.session.scalar(
                select(DocumentRagIndex.text_extraction_id).where(
                    DocumentRagIndex.id == passage.index_id
                )
            )
            page_numbers = sorted(
                {item.page_number for item in context},
                key=lambda page: (page != passage.page_number, page),
            )
            for page in page_numbers:
                page_context = "\n".join(
                    "\n".join(part for part in (item.section, item.content_text) if part)
                    for item in context
                    if item.page_number == page
                )
                if any(
                    item.document_id == document.id
                    and item.page_number == page
                    and item.content_text == page_context
                    for item in evidence
                ):
                    continue
                evidence.append(
                    RetrievedEvidence(
                        document_id=document.id,
                        title=document.title,
                        original_filename=document.original_filename,
                        page_number=page,
                        content_text=page_context,
                        score=score,
                        lexical_score=0,
                        document_type=document.document_type,
                        text_extraction_id=source_id,
                    )
                )
                if len(evidence) == 3:
                    break
            if len(evidence) == 3:
                break
        return tuple(evidence)
