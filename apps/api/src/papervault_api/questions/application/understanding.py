import asyncio
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from papervault_api.core.model_clients import ModelClient
from papervault_api.documents.infrastructure.models import Document, DocumentTextExtraction
from papervault_api.questions.application.evidence_analysis import (
    FINDINGS_VERSION,
    extract_findings,
)
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex, DocumentRagPassage


class AnalysisSuperseded(Exception):
    pass


class DocumentUnderstandingService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        client: ModelClient,
        pipeline: str,
        model_digest: str | None,
    ) -> None:
        self.factory = factory
        self.client = client
        self.pipeline = pipeline
        self.model_digest = model_digest

    def current_index(self, index_id: UUID) -> Select[tuple[DocumentRagIndex]]:
        return (
            select(DocumentRagIndex)
            .join(
                DocumentTextExtraction,
                DocumentTextExtraction.id == DocumentRagIndex.text_extraction_id,
            )
            .join(Document, Document.id == DocumentRagIndex.document_id)
            .where(
                DocumentRagIndex.id == index_id,
                DocumentRagIndex.pipeline_id == self.pipeline,
                DocumentRagIndex.status == "ready",
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == "succeeded",
                Document.status == "ready",
                Document.archived_at.is_(None),
            )
            .with_for_update(of=DocumentRagIndex)
        )

    async def process(self, index_id: UUID) -> bool:
        run_id = str(uuid4())
        async with self.factory() as session:
            index = await session.scalar(self.current_index(index_id))
            if index is None:
                return False
            same_protocol = (
                index.understanding.get("model") == self.client.chat_model
                and index.understanding.get("model_digest") == self.model_digest
                and index.understanding.get("prompt_version") == FINDINGS_VERSION
            )
            if same_protocol and index.understanding.get("status") == "needs_review":
                return False
            checkpoint = dict(index.understanding) if same_protocol else {}
            checkpoint.pop("error", None)
            index.understanding = {
                **checkpoint,
                "status": "processing",
                "model": self.client.chat_model,
                "model_digest": self.model_digest,
                "prompt_version": FINDINGS_VERSION,
                "run_id": run_id,
            }
            records = list(
                (
                    await session.scalars(
                        select(DocumentRagPassage)
                        .where(
                            DocumentRagPassage.index_id == index_id,
                        )
                        .order_by(DocumentRagPassage.ordinal)
                    )
                ).all()
            )
            passages = [
                {
                    "ordinal": passage.ordinal,
                    "page_number": passage.page_number,
                    "section": passage.section,
                    "text": passage.content_text,
                }
                for passage in records
            ]
            index.understanding = {**index.understanding, "total_passages": len(passages)}
            await session.commit()
        loop = asyncio.get_running_loop()

        def progress(state: dict[str, Any]) -> None:
            future = asyncio.run_coroutine_threadsafe(self.publish(index_id, run_id, state), loop)
            if not future.result():
                raise AnalysisSuperseded

        try:
            result = await asyncio.to_thread(
                extract_findings, self.client, passages, progress=progress, checkpoint=checkpoint
            )
            return await self.publish(index_id, run_id, result)
        except AnalysisSuperseded:
            return False
        except Exception:
            await self.publish(
                index_id, run_id, {"status": "failed", "error": "local_analysis_failed"}
            )
            raise

    async def publish(self, index_id: UUID, run_id: str, state: dict[str, Any]) -> bool:
        async with self.factory() as session:
            index = await session.scalar(self.current_index(index_id))
            if index is None or index.understanding.get("run_id") != run_id:
                return False
            index.understanding = {**index.understanding, **state, "run_id": run_id}
            await session.commit()
            return True
