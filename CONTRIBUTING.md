# Contributing to PaperVault

PaperVault values maintainability over speed. Changes should be small, tested, and aligned with the existing architecture.

## Development Standards

- Keep controllers and task handlers thin.
- Put business workflows in application-level services/use cases.
- Hide external systems behind provider interfaces.
- Prefer explicit code over magic.
- Add tests at the lowest useful level.
- Do not store document blobs in PostgreSQL.

## Local Checks

Backend:

```bash
cd apps/api
ruff check src tests
mypy src
pytest
```

Frontend:

```bash
cd apps/web
npm run lint
npm test -- --run
```

## Architecture Decisions

Material decisions should be recorded in `docs/adr`.
