# PaperVault

PaperVault is a self-hosted document management system for turning PDFs, scans, and images into a private searchable knowledge base. Original files remain in S3-compatible object storage while PostgreSQL stores metadata, audit history, tags, users, and processing state. OpenSearch provides full-text and vector search.

## What PaperVault Does

- Upload PDFs, scanned PDFs, JPEGs, and PNGs.
- Extract embedded text and fall back to Tesseract OCR for scans.
- Classify common financial, employment, identity, medical, education, property, and purchase documents.
- Generate summaries, keywords, entities, suggested tags, typed structured metadata, and embeddings.
- Search by keyword, meaning, document type, date, tag, issuer, organization, or combined filters.
- Ask natural-language questions and receive evidence-backed answers with document and page citations.
- Save searches and revisit recent queries.
- Read documents in a built-in page-aware viewer with text-layer and OCR-coordinate highlighting.
- Review incomplete or low-confidence extraction results in a dedicated quality queue.
- Replace or restore source files without losing immutable version history, and compare extracted text between versions.
- Browse a vault-wide activity feed and permanently remove users with their owned files.
- Detect exact-file, exact-text, content-similar, and OCR-similar duplicates with explainable scores and confirmation-gated archival.
- Track metadata edits, tag changes, archive actions, versions, reminders, and duplicate resolution.
- Use local accounts or OIDC providers such as Authentik and Keycloak.
- Administer registration, user access, roles, and active runtime providers from the web app.

The complete capability matrix and planned work are documented in [Product Scope](docs/product-scope.md).

## Architecture

PaperVault is a modular monolith with separate runtime processes:

- `apps/api`: FastAPI, application services, SQLAlchemy models, provider adapters, and Alembic migrations.
- `apps/worker`: Celery worker image built from the backend package.
- `apps/web`: React, TypeScript, Vite, TanStack Query/Router, Tailwind, and reusable UI primitives.
- `infra`: Docker Compose, Kubernetes, Helm, Gateway API, and deployment configuration.
- `docs`: architecture, operations, API reference, and decision records.

HTTP routes and Celery tasks are orchestration boundaries. Document, identity, administration, search, question answering, tagging, notification, and lifecycle behavior belongs to feature-owned application services. OCR, AI, embeddings, grounded answers, storage, OIDC, and search engines are accessed through provider interfaces.

See [Architecture](docs/architecture.md) for the system model and data flows.

## Quick Start

Prerequisites:

- Docker with Docker Compose
- At least 8 GB of available memory for the complete local stack

Create local configuration and start the services:

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web app: `http://localhost:5173`
- API health: `http://localhost:8000/health`
- MinIO console: `http://localhost:9001`
- OpenSearch: `http://localhost:9200`

The first registered account becomes an administrator. Before exposing an instance publicly, replace every default secret, disable development identity headers, and decide whether open registration should remain enabled.

## Production Deployment

The Helm chart deploys the API, worker, web frontend, migration job, services, health probes, and an optional Gateway API `HTTPRoute`. Production deployments should use externally managed PostgreSQL, Redis, object storage, and OpenSearch with tested backups.

Read [Deployment](docs/deployment.md) before installing outside a development environment.

## Development

Backend:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
pytest
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Detailed setup, Windows commands, provider configuration, and validation steps are in [Developer Setup](docs/development.md).

## Documentation

- [Product scope and roadmap](docs/product-scope.md)
- [Architecture](docs/architecture.md)
- [Database](docs/database.md)
- [API](docs/api.md)
- [Deployment](docs/deployment.md)
- [Contributing](CONTRIBUTING.md)
- [Architecture decision records](docs/adr)

## License

PaperVault is available under the [MIT License](LICENSE).
