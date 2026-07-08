# PaperVault

PaperVault is a production-oriented, self-hostable personal document management system. It turns PDFs, scanned PDFs, and images into a searchable knowledge base with OCR, metadata extraction, AI summaries, semantic search, timelines, duplicate detection, and notifications.

This repository is being built iteratively. Phase 1 established the foundation. Phase 2 added the core domain registry, relational schema, migrations, and persistence boundaries. Phase 3 added uploads, object storage, processing jobs, and text-extraction records. Phase 4 added AI analysis and embedding provider boundaries. Phase 5 added the first usable knowledge-base layer. Phase 6 added local JWT authentication, password hashing, RBAC dependencies, admin user management, and a frontend auth gate. Phase 7 added a self-hosted OCR adapter for scanned PDFs and images. Phase 8 added OpenSearch indexing and reindexing infrastructure. Phase 9 adds GHCR image publishing and a deployable Helm chart.

## Architecture

PaperVault starts as a modular monolith with explicit boundaries:

- `apps/api`: FastAPI HTTP API, configuration, observability, database setup, route composition, domain modules, and persistence adapters.
- `apps/worker`: Celery worker container using the backend package.
- `apps/web`: React, TypeScript, Vite, TanStack Router, TanStack Query, Tailwind, shadcn-style primitives.
- `infra`: Docker Compose, Kubernetes, and Helm deployment assets.
- `docs`: architecture documentation and ADRs.

The first durable boundary is between orchestration and domain logic. HTTP routes and Celery tasks should remain thin. Business workflows belong in application services/use cases. Provider-specific integrations such as OCR, embeddings, object storage, and search should sit behind interfaces so implementations can be swapped.

## Local Development

Copy the environment template:

```bash
cp .env.example .env
```

Start the stack:

```bash
docker compose up --build
```

Expected local services:

- API: `http://localhost:8000`
- API health: `http://localhost:8000/health`
- Web: `http://localhost:5173`
- MinIO console: `http://localhost:9001`
- OpenSearch: `http://localhost:9200`

## Current Status

Phase 9 includes GitHub Actions image publishing to GHCR, Helm chart workload resources, migration hooks, services, secrets/config wiring, Kubernetes server-side validation, and hardened non-root container defaults. OIDC login, OpenSearch-backed query execution, richer OCR language packs, and dependency subcharts are planned for later phases after approval.

## License

MIT. See [LICENSE](LICENSE).
