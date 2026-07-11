from __future__ import annotations

import asyncio
import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.documents.domain.enums import (
    DocumentStatus,
    TextExtractionSource,
    TextExtractionStatus,
)
from papervault_api.documents.infrastructure.models import (
    Document,
    DocumentDuplicateBucket,
    DocumentDuplicateFingerprint,
    DocumentTextExtraction,
)

FINGERPRINT_ALGORITHM_VERSION = 1
MINHASH_SIGNATURE_SIZE = 32
MINHASH_BAND_SIZE = 4
SHINGLE_SIZE = 3
MAX_FINGERPRINT_TOKENS = 50_000
MAX_BUCKET_MEMBERS = 100
MIN_LENGTH_SIMILARITY = 0.75

DuplicateMethod = Literal[
    "sha256_hash",
    "normalized_text",
    "content_similarity",
    "ocr_similarity",
]

EXACT_FILE_METHOD: DuplicateMethod = "sha256_hash"
EXACT_TEXT_METHOD: DuplicateMethod = "normalized_text"
CONTENT_SIMILARITY_METHOD: DuplicateMethod = "content_similarity"
OCR_SIMILARITY_METHOD: DuplicateMethod = "ocr_similarity"

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class TextFingerprint:
    normalized_text_sha256: str
    minhash_signature: tuple[int, ...]
    token_count: int
    shingle_count: int
    character_count: int
    bucket_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicateSignals:
    text_similarity: float
    length_similarity: float
    shared_bands: int


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    method: DuplicateMethod
    confidence: float
    requires_confirmation: bool
    explanation: str
    signals: DuplicateSignals
    documents: tuple[Document, ...]


@dataclass(frozen=True, slots=True)
class DuplicateRefreshResult:
    scanned: int
    updated: int
    skipped: int


@dataclass(frozen=True, slots=True)
class DuplicateValidation:
    method: DuplicateMethod
    confidence: float
    requires_confirmation: bool


def build_text_fingerprint(text: str, *, min_tokens: int) -> TextFingerprint | None:
    normalized_unicode = unicodedata.normalize("NFKC", text).casefold()
    tokens = TOKEN_PATTERN.findall(normalized_unicode)[:MAX_FINGERPRINT_TOKENS]
    if len(tokens) < min_tokens:
        return None

    normalized_text = " ".join(tokens)
    shingles = {
        " ".join(tokens[index : index + SHINGLE_SIZE]).encode("utf-8")
        for index in range(len(tokens) - SHINGLE_SIZE + 1)
    }
    if not shingles:
        return None

    signature = tuple(
        min(
            int.from_bytes(
                hashlib.blake2b(
                    seed.to_bytes(2, "big") + b":" + shingle,
                    digest_size=8,
                ).digest(),
                "big",
            )
            for shingle in shingles
        )
        for seed in range(MINHASH_SIGNATURE_SIZE)
    )
    bucket_hashes = tuple(
        hashlib.sha256(
            ",".join(str(value) for value in signature[offset : offset + MINHASH_BAND_SIZE]).encode(
                "ascii"
            )
        ).hexdigest()[:32]
        for offset in range(0, MINHASH_SIGNATURE_SIZE, MINHASH_BAND_SIZE)
    )
    return TextFingerprint(
        normalized_text_sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        minhash_signature=signature,
        token_count=len(tokens),
        shingle_count=len(shingles),
        character_count=len(normalized_text),
        bucket_hashes=bucket_hashes,
    )


def compare_fingerprints(
    left: DocumentDuplicateFingerprint,
    right: DocumentDuplicateFingerprint,
    *,
    shared_bands: int,
) -> DuplicateSignals:
    signature_size = min(len(left.minhash_signature), len(right.minhash_signature))
    if signature_size == 0:
        text_similarity = 0.0
    else:
        matching = sum(
            left.minhash_signature[index] == right.minhash_signature[index]
            for index in range(signature_size)
        )
        text_similarity = matching / signature_size
    length_similarity = min(left.token_count, right.token_count) / max(
        left.token_count,
        right.token_count,
    )
    return DuplicateSignals(
        text_similarity=round(text_similarity, 4),
        length_similarity=round(length_similarity, 4),
        shared_bands=shared_bands,
    )


class DuplicateDetectionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        content_similarity_threshold: float = 0.88,
        ocr_similarity_threshold: float = 0.84,
        min_tokens: int = 24,
    ) -> None:
        self._session = session
        self._content_similarity_threshold = content_similarity_threshold
        self._ocr_similarity_threshold = ocr_similarity_threshold
        self._min_tokens = min_tokens

    async def refresh_document(self, document_id: UUID) -> bool:
        row = (
            await self._session.execute(
                select(Document, DocumentTextExtraction)
                .join(
                    DocumentTextExtraction,
                    DocumentTextExtraction.document_id == Document.id,
                )
                .where(
                    Document.id == document_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                    DocumentTextExtraction.is_current.is_(True),
                    DocumentTextExtraction.status == TextExtractionStatus.SUCCEEDED.value,
                    DocumentTextExtraction.content_text.is_not(None),
                )
            )
        ).one_or_none()
        if row is None:
            await self._session.execute(
                delete(DocumentDuplicateFingerprint).where(
                    DocumentDuplicateFingerprint.document_id == document_id
                )
            )
            await self._session.commit()
            return False

        document, extraction = row
        updated = await self._upsert(document, extraction)
        await self._session.commit()
        return updated

    async def refresh_owner(self, owner_id: UUID, *, limit: int = 100) -> DuplicateRefreshResult:
        rows = (
            await self._session.execute(
                select(Document, DocumentTextExtraction)
                .join(
                    DocumentTextExtraction,
                    DocumentTextExtraction.document_id == Document.id,
                )
                .outerjoin(
                    DocumentDuplicateFingerprint,
                    DocumentDuplicateFingerprint.document_id == Document.id,
                )
                .where(
                    Document.owner_id == owner_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                    DocumentTextExtraction.is_current.is_(True),
                    DocumentTextExtraction.status == TextExtractionStatus.SUCCEEDED.value,
                    DocumentTextExtraction.content_text.is_not(None),
                    or_(
                        DocumentDuplicateFingerprint.id.is_(None),
                        DocumentDuplicateFingerprint.text_extraction_id
                        != DocumentTextExtraction.id,
                        DocumentDuplicateFingerprint.algorithm_version
                        != FINGERPRINT_ALGORITHM_VERSION,
                    ),
                )
                .order_by(Document.updated_at.asc())
                .limit(limit)
            )
        ).all()

        updated = 0
        skipped = 0
        for document, extraction in rows:
            if await self._upsert(document, extraction):
                updated += 1
            else:
                skipped += 1
        await self._session.commit()
        return DuplicateRefreshResult(scanned=len(rows), updated=updated, skipped=skipped)

    async def list_candidates(self, owner_id: UUID) -> tuple[DuplicateCandidate, ...]:
        documents = tuple(
            (
                await self._session.execute(
                    select(Document)
                    .where(
                        Document.owner_id == owner_id,
                        Document.status != DocumentStatus.ARCHIVED.value,
                    )
                    .order_by(Document.created_at.asc())
                )
            ).scalars()
        )
        candidates: list[DuplicateCandidate] = []
        covered_pairs: set[tuple[UUID, UUID]] = set()

        documents_by_hash: dict[str, list[Document]] = defaultdict(list)
        for document in documents:
            documents_by_hash[document.sha256_hash].append(document)
        for exact_file_group in documents_by_hash.values():
            if len(exact_file_group) < 2:
                continue
            for left_document, right_document in combinations(exact_file_group, 2):
                covered_pairs.add(_pair_key(left_document.id, right_document.id))
            candidates.append(
                DuplicateCandidate(
                    method=EXACT_FILE_METHOD,
                    confidence=1.0,
                    requires_confirmation=False,
                    explanation="Files have identical SHA-256 hashes.",
                    signals=DuplicateSignals(1.0, 1.0, 0),
                    documents=tuple(exact_file_group),
                )
            )

        fingerprint_rows = (
            await self._session.execute(
                select(DocumentDuplicateFingerprint, Document)
                .join(Document, Document.id == DocumentDuplicateFingerprint.document_id)
                .join(
                    DocumentTextExtraction,
                    DocumentTextExtraction.id == DocumentDuplicateFingerprint.text_extraction_id,
                )
                .where(
                    Document.owner_id == owner_id,
                    Document.status != DocumentStatus.ARCHIVED.value,
                    DocumentDuplicateFingerprint.algorithm_version == FINGERPRINT_ALGORITHM_VERSION,
                    DocumentTextExtraction.is_current.is_(True),
                )
            )
        ).all()
        by_fingerprint_id: dict[
            UUID,
            tuple[DocumentDuplicateFingerprint, Document],
        ] = {fingerprint.id: (fingerprint, document) for fingerprint, document in fingerprint_rows}

        by_normalized_hash: dict[str, list[tuple[DocumentDuplicateFingerprint, Document]]] = (
            defaultdict(list)
        )
        for fingerprint, document in fingerprint_rows:
            by_normalized_hash[fingerprint.normalized_text_sha256].append((fingerprint, document))
        for exact_text_group in by_normalized_hash.values():
            unique_by_file_hash: dict[
                str,
                tuple[DocumentDuplicateFingerprint, Document],
            ] = {}
            for entry in exact_text_group:
                unique_by_file_hash.setdefault(entry[1].sha256_hash, entry)
            representatives = tuple(unique_by_file_hash.values())
            for left_entry, right_entry in combinations(exact_text_group, 2):
                covered_pairs.add(_pair_key(left_entry[1].id, right_entry[1].id))
            if len(representatives) < 2:
                continue

            token_counts = [entry[0].token_count for entry in representatives]
            candidates.append(
                DuplicateCandidate(
                    method=EXACT_TEXT_METHOD,
                    confidence=1.0,
                    requires_confirmation=True,
                    explanation=(
                        "Extracted text is identical after Unicode, case, and whitespace "
                        "normalization."
                    ),
                    signals=DuplicateSignals(
                        1.0,
                        round(min(token_counts) / max(token_counts), 4),
                        MINHASH_SIGNATURE_SIZE // MINHASH_BAND_SIZE,
                    ),
                    documents=tuple(entry[1] for entry in representatives),
                )
            )

        if by_fingerprint_id:
            bucket_rows = (
                await self._session.execute(
                    select(DocumentDuplicateBucket).where(
                        DocumentDuplicateBucket.fingerprint_id.in_(by_fingerprint_id)
                    )
                )
            ).scalars()
            bucket_members: dict[tuple[int, str], list[UUID]] = defaultdict(list)
            for bucket in bucket_rows:
                bucket_members[(bucket.band_index, bucket.bucket_hash)].append(
                    bucket.fingerprint_id
                )

            shared_band_counts: dict[tuple[UUID, UUID], int] = defaultdict(int)
            for members in bucket_members.values():
                if len(members) < 2 or len(members) > MAX_BUCKET_MEMBERS:
                    continue
                for left_id, right_id in combinations(members, 2):
                    shared_band_counts[_pair_key(left_id, right_id)] += 1

            for fingerprint_pair, shared_bands in shared_band_counts.items():
                left_entry = by_fingerprint_id[fingerprint_pair[0]]
                right_entry = by_fingerprint_id[fingerprint_pair[1]]
                document_pair = _pair_key(left_entry[1].id, right_entry[1].id)
                if document_pair in covered_pairs:
                    continue
                signals = compare_fingerprints(
                    left_entry[0],
                    right_entry[0],
                    shared_bands=shared_bands,
                )
                method = _similarity_method(left_entry[0], right_entry[0])
                threshold = self._threshold_for(method)
                if (
                    signals.text_similarity < threshold
                    or signals.length_similarity < MIN_LENGTH_SIMILARITY
                ):
                    continue
                confidence = round(
                    signals.text_similarity * (0.9 + 0.1 * signals.length_similarity),
                    4,
                )
                covered_pairs.add(document_pair)
                candidates.append(
                    DuplicateCandidate(
                        method=method,
                        confidence=confidence,
                        requires_confirmation=True,
                        explanation=_similarity_explanation(method, signals),
                        signals=signals,
                        documents=(left_entry[1], right_entry[1]),
                    )
                )

        method_priority = {
            EXACT_FILE_METHOD: 0,
            EXACT_TEXT_METHOD: 1,
            CONTENT_SIMILARITY_METHOD: 2,
            OCR_SIMILARITY_METHOD: 3,
        }
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    method_priority[candidate.method],
                    -candidate.confidence,
                    candidate.documents[0].created_at,
                ),
            )
        )

    async def validate_pair(
        self,
        *,
        owner_id: UUID,
        keep_document: Document,
        duplicate_document: Document,
        requested_method: str,
    ) -> DuplicateValidation | None:
        if keep_document.owner_id != owner_id or duplicate_document.owner_id != owner_id:
            return None
        if keep_document.sha256_hash == duplicate_document.sha256_hash:
            return DuplicateValidation(EXACT_FILE_METHOD, 1.0, False)

        fingerprints = tuple(
            (
                await self._session.execute(
                    select(DocumentDuplicateFingerprint)
                    .join(
                        DocumentTextExtraction,
                        DocumentTextExtraction.id
                        == DocumentDuplicateFingerprint.text_extraction_id,
                    )
                    .where(
                        DocumentDuplicateFingerprint.document_id.in_(
                            (keep_document.id, duplicate_document.id)
                        ),
                        DocumentDuplicateFingerprint.algorithm_version
                        == FINGERPRINT_ALGORITHM_VERSION,
                        DocumentTextExtraction.is_current.is_(True),
                    )
                )
            ).scalars()
        )
        if len(fingerprints) != 2:
            return None
        by_document = {fingerprint.document_id: fingerprint for fingerprint in fingerprints}
        left = by_document.get(keep_document.id)
        right = by_document.get(duplicate_document.id)
        if left is None or right is None:
            return None
        if left.normalized_text_sha256 == right.normalized_text_sha256:
            if requested_method != EXACT_TEXT_METHOD:
                return None
            return DuplicateValidation(EXACT_TEXT_METHOD, 1.0, True)

        method = _similarity_method(left, right)
        if requested_method != method:
            return None
        signals = compare_fingerprints(left, right, shared_bands=0)
        if (
            signals.text_similarity < self._threshold_for(method)
            or signals.length_similarity < MIN_LENGTH_SIMILARITY
        ):
            return None
        confidence = round(
            signals.text_similarity * (0.9 + 0.1 * signals.length_similarity),
            4,
        )
        return DuplicateValidation(method, confidence, True)

    async def _upsert(
        self,
        document: Document,
        extraction: DocumentTextExtraction,
    ) -> bool:
        if not extraction.content_text:
            return False
        built = await asyncio.to_thread(
            build_text_fingerprint,
            extraction.content_text,
            min_tokens=self._min_tokens,
        )
        existing = await self._session.scalar(
            select(DocumentDuplicateFingerprint).where(
                DocumentDuplicateFingerprint.document_id == document.id
            )
        )
        if built is None:
            if existing is not None:
                await self._session.delete(existing)
            return False
        if (
            existing is not None
            and existing.text_extraction_id == extraction.id
            and existing.algorithm_version == FINGERPRINT_ALGORITHM_VERSION
            and existing.normalized_text_sha256 == built.normalized_text_sha256
        ):
            return False

        if existing is None:
            existing = DocumentDuplicateFingerprint(
                document_id=document.id,
                text_extraction_id=extraction.id,
                source=extraction.source,
                algorithm_version=FINGERPRINT_ALGORITHM_VERSION,
                normalized_text_sha256=built.normalized_text_sha256,
                minhash_signature=list(built.minhash_signature),
                token_count=built.token_count,
                shingle_count=built.shingle_count,
                character_count=built.character_count,
            )
            self._session.add(existing)
            await self._session.flush()
        else:
            existing.text_extraction_id = extraction.id
            existing.source = extraction.source
            existing.algorithm_version = FINGERPRINT_ALGORITHM_VERSION
            existing.normalized_text_sha256 = built.normalized_text_sha256
            existing.minhash_signature = list(built.minhash_signature)
            existing.token_count = built.token_count
            existing.shingle_count = built.shingle_count
            existing.character_count = built.character_count
            await self._session.execute(
                delete(DocumentDuplicateBucket).where(
                    DocumentDuplicateBucket.fingerprint_id == existing.id
                )
            )

        self._session.add_all(
            DocumentDuplicateBucket(
                fingerprint_id=existing.id,
                band_index=band_index,
                bucket_hash=bucket_hash,
            )
            for band_index, bucket_hash in enumerate(built.bucket_hashes)
        )
        return True

    def _threshold_for(self, method: DuplicateMethod) -> float:
        if method == OCR_SIMILARITY_METHOD:
            return self._ocr_similarity_threshold
        return self._content_similarity_threshold


def _pair_key(left: UUID, right: UUID) -> tuple[UUID, UUID]:
    return (left, right) if left.int < right.int else (right, left)


def _similarity_method(
    left: DocumentDuplicateFingerprint,
    right: DocumentDuplicateFingerprint,
) -> DuplicateMethod:
    if TextExtractionSource.OCR.value in {left.source, right.source}:
        return OCR_SIMILARITY_METHOD
    return CONTENT_SIMILARITY_METHOD


def _similarity_explanation(method: DuplicateMethod, signals: DuplicateSignals) -> str:
    similarity = round(signals.text_similarity * 100)
    length = round(signals.length_similarity * 100)
    if method == OCR_SIMILARITY_METHOD:
        return (
            f"OCR-tolerant text fingerprints are {similarity}% similar with {length}% "
            "relative text length."
        )
    return (
        f"Extracted-text fingerprints are {similarity}% similar with {length}% relative "
        "text length."
    )
