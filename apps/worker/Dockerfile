FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 10001 papervault \
    && adduser --system --uid 10001 --ingroup papervault --no-create-home papervault

COPY apps/api/pyproject.toml apps/api/README.md ./
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations

RUN pip install --upgrade pip && pip install .

USER 10001:10001

CMD ["celery", "-A", "papervault_api.worker.celery_app:celery_app", "worker", "--loglevel=INFO"]
