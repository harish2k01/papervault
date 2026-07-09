# Developer Setup

## Prerequisites

- Docker and Docker Compose
- Python 3.13
- Node.js 22 or newer

## Backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Run migrations:

```bash
alembic upgrade head
```

Upload API requests currently require development identity headers:

```bash
curl -X POST http://localhost:8000/documents/uploads \
  -H "X-PaperVault-User-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-PaperVault-User-Email: local@example.com" \
  -F "document_type=generic_pdf" \
  -F "file=@example.pdf;type=application/pdf"
```

AI processing is enabled by default with local deterministic providers:

```env
PAPERVAULT_AI_ENABLED=true
PAPERVAULT_AI_PROVIDER=local
PAPERVAULT_EMBEDDING_PROVIDER=local
PAPERVAULT_EMBEDDING_DIMENSIONS=64
```

These providers require no external credentials. Model-backed providers can be added behind the same interfaces.

OCR is enabled by default through local Tesseract and Poppler commands:

```env
PAPERVAULT_OCR_PROVIDER=tesseract
PAPERVAULT_OCR_LANGUAGES=eng
PAPERVAULT_OCR_MAX_PDF_PAGES=50
```

The worker container installs `tesseract-ocr` and `poppler-utils`. For non-container development, install those binaries locally or set `PAPERVAULT_OCR_PROVIDER=unavailable` to keep scanned-document processing as an explicit failure.

OpenSearch indexing is enabled by default:

```env
PAPERVAULT_SEARCH_INDEX_ENABLED=true
PAPERVAULT_SEARCH_QUERY_BACKEND=opensearch
PAPERVAULT_SEARCH_QUERY_FALLBACK_ENABLED=true
OPENSEARCH_DOCUMENTS_INDEX=papervault-documents-v1
OPENSEARCH_TIMEOUT_SECONDS=5
```

The worker indexes documents after text extraction, AI processing, and notification generation. User-facing search uses OpenSearch when it is enabled and falls back to the database-backed scorer if OpenSearch is unavailable. Use `POST /search/index/rebuild` to rebuild the current user's index projection after changing mappings or adapter behavior.

The frontend uses the same temporary development identity headers as the API. A generated development user id is stored in browser `localStorage` under `papervault.devUserId`.

Phase 6 adds local JWT authentication. The frontend stores the current bearer token in browser `localStorage` under `papervault.accessToken`. Development headers remain available only when:

```env
PAPERVAULT_AUTH_ALLOW_DEV_HEADERS=true
PAPERVAULT_ENV=development
```

The first registered local account becomes an administrator. Disable open registration before exposing a deployment to untrusted users:

```env
PAPERVAULT_LOCAL_REGISTRATION_ENABLED=false
PAPERVAULT_AUTH_ALLOW_DEV_HEADERS=false
JWT_SIGNING_KEY=<replace-with-a-long-random-secret>
```

On Windows PowerShell:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## Frontend

```bash
cd apps/web
npm install
npm run dev
```

## Full Stack

```bash
cp .env.example .env
docker compose up --build
```

## Helm Validation

The Helm chart can be rendered and validated against a Kubernetes API without installing workloads:

```bash
kubectl create namespace papervault --dry-run=client -o yaml | kubectl apply -f -
helm lint infra/helm/papervault
helm template papervault infra/helm/papervault --namespace papervault > rendered.yaml
kubectl apply --dry-run=server -f rendered.yaml --namespace papervault
helm upgrade --install papervault infra/helm/papervault --namespace papervault --dry-run=server
```

After a deployed upgrade, run the chart smoke test:

```bash
helm test papervault --namespace papervault
```

For a public-route workflow smoke test:

```bash
python scripts/cluster_smoke.py --base-url https://papervault.example.com/api
```
