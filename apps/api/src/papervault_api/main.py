from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from papervault_api.api.router import api_router
from papervault_api.core.config import get_settings
from papervault_api.core.logging import configure_logging
from papervault_api.core.observability import configure_observability
from papervault_api.db import models as _models  # noqa: F401


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PaperVault API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    configure_observability(app, settings)
    return app
