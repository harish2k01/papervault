from celery import Celery  # type: ignore[import-untyped]

from papervault_api.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "papervault",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "papervault_api.worker.tasks.documents",
        "papervault_api.worker.tasks.health",
    ],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
