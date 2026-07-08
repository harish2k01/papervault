from papervault_api.worker.celery_app import celery_app


@celery_app.task(name="papervault.health.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
