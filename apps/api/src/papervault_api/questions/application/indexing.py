import asyncio
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.application.storage import ObjectStorage
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentTextExtraction,
    DocumentTextPage,
)
from papervault_api.questions.application.structure import structured_passages
from papervault_api.questions.infrastructure.local_inference import (
    InferenceUnavailable,
    LayoutParser,
    SemanticModels,
)
from papervault_api.questions.infrastructure.rag_models import DocumentRagIndex, DocumentRagPassage


class StructuredIndexingService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        parser: LayoutParser,
        models: SemanticModels,
        pipeline: str,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser = parser
        self.models = models
        self.pipeline = pipeline

    async def build(self, document_id: UUID, extraction_id: UUID) -> bool:
        source = await self.session.scalar(
            select(DocumentTextExtraction).where(
                DocumentTextExtraction.id == extraction_id,
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
                DocumentTextExtraction.status == "succeeded",
            )
        )
        document = await self.session.get(Document, document_id)
        if source is None or document is None or document.status != "ready":
            return False
        existing = await self.session.scalar(
            select(DocumentRagIndex).where(
                DocumentRagIndex.text_extraction_id == extraction_id,
                DocumentRagIndex.pipeline_id == self.pipeline,
            )
        )
        if existing is not None and existing.status == "ready":
            return False
        source_pages = list(
            (
                await self.session.scalars(
                    select(DocumentTextPage).where(
                        DocumentTextPage.text_extraction_id == extraction_id,
                    )
                )
            ).all()
        )
        required_pages = {page.page_number for page in source_pages if page.content_text.strip()}
        snapshot = (document.storage_key, document.sha256_hash)
        with TemporaryDirectory(prefix="papervault-structure-") as folder:
            path = Path(folder) / "source"
            await self.storage.download_to_file(
                bucket=document.storage_bucket, key=document.storage_key, destination=path
            )
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != snapshot[1]:
                raise InferenceUnavailable("Structured conversion source hash mismatch")
            parsed = await asyncio.to_thread(self.parser.parse, content, document.content_type)
        passages = structured_passages(parsed)
        covered = sorted({passage.page for passage in passages})
        page_count = len(parsed.get("pages", {}))
        if not passages or page_count != source.page_count or not required_pages.issubset(covered):
            raise InferenceUnavailable("Structured conversion has incomplete page coverage")
        vectors: list[list[float]] = []
        for start in range(0, len(passages), 16):
            vectors.extend(
                await asyncio.to_thread(
                    self.models.embed,
                    [
                        passage.section + "\n" + passage.text
                        for passage in passages[start : start + 16]
                    ],
                )
            )
        # The source may have changed or been deleted during inference. Lock only for
        # publication, and refresh cached ORM state before checking the source again.
        current = await self.session.scalar(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        fresh_source = await self.session.scalar(
            select(DocumentTextExtraction.id).where(
                DocumentTextExtraction.document_id == document_id,
                DocumentTextExtraction.is_current.is_(True),
            )
        )
        if (
            current is None
            or current.status != "ready"
            or fresh_source != extraction_id
            or (current.storage_key, current.sha256_hash) != snapshot
        ):
            await self.session.rollback()
            return False
        # A concurrent redelivery that finished while this one was inferring wins.
        existing = await self.session.scalar(
            select(DocumentRagIndex)
            .execution_options(populate_existing=True)
            .where(
                DocumentRagIndex.text_extraction_id == extraction_id,
                DocumentRagIndex.pipeline_id == self.pipeline,
            )
        )
        if existing is not None and existing.status == "ready":
            await self.session.rollback()
            return False
        index = existing or DocumentRagIndex(
            document_id=document_id,
            text_extraction_id=extraction_id,
            pipeline_id=self.pipeline,
            parser_model=self.parser.identity,
            embedding_model=self.models.model,
            embedding_revision=self.models.revision,
            dimensions=self.models.dimensions,
            status="ready",
            page_count=page_count,
            covered_pages=covered,
            warnings=[],
            understanding={},
        )
        index.status = "ready"
        index.page_count = page_count
        index.covered_pages = covered
        index.warnings = []
        self.session.add(index)
        await self.session.flush()
        self.session.add_all(
            [
                DocumentRagPassage(
                    index_id=index.id,
                    ordinal=ordinal,
                    page_number=passage.page,
                    kind=passage.kind,
                    section=passage.section,
                    content_text=passage.text,
                    provenance=passage.provenance,
                    vector=vector,
                )
                for ordinal, (passage, vector) in enumerate(zip(passages, vectors, strict=True))
            ]
        )
        await self.session.commit()
        return True
