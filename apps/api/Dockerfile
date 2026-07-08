FROM python:3.13-slim AS base

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

EXPOSE 8000

CMD ["uvicorn", "papervault_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
