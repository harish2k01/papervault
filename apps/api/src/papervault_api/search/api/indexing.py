from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from papervault_api.core.config import Settings
from papervault_api.search.application.indexing import SearchIndexingService
from papervault_api.search.infrastructure.opensearch import (
    OpenSearchError,
    build_search_document_index,
)

logger = structlog.get_logger(__name__)


async def reindex_document_best_effort(
    *,
    session: AsyncSession,
    settings: Settings,
    document_id: UUID,
    reason: str,
) -> None:
    service = SearchIndexingService(
        session=session,
        search_index=build_search_document_index(settings),
    )
    try:
        await service.index_document(document_id)
    except OpenSearchError as exc:
        logger.warning(
            "document_search_projection_refresh_failed",
            document_id=str(document_id),
            reason=reason,
            error=str(exc),
        )
