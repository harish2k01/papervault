FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system papervault && adduser --system --ingroup papervault papervault

COPY apps/api/pyproject.toml apps/api/README.md ./
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations

RUN pip install --upgrade pip && pip install .

USER papervault

CMD ["celery", "-A", "papervault_api.worker.celery_app:celery_app", "worker", "--loglevel=INFO"]
