from fastapi import APIRouter

from papervault_api.administration.api.routes import router as administration_router
from papervault_api.api.routes import health
from papervault_api.collections.api.routes import router as collections_router
from papervault_api.documents.api.routes import router as documents_router
from papervault_api.identity.api.routes import router as identity_router
from papervault_api.notifications.api.routes import router as notifications_router
from papervault_api.questions.api.routes import router as questions_router
from papervault_api.search.api.routes import router as search_router
from papervault_api.tags.api.routes import router as tags_router
from papervault_api.timeline.api.routes import router as timeline_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(administration_router)
api_router.include_router(collections_router)
api_router.include_router(identity_router)
api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(tags_router)
api_router.include_router(notifications_router)
api_router.include_router(questions_router)
api_router.include_router(timeline_router)
