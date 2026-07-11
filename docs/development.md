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

When development identity headers are enabled, upload API requests can use:

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
PAPERVAULT_ANSWER_PROVIDER=local
PAPERVAULT_EMBEDDING_PROVIDER=local
PAPERVAULT_EMBEDDING_DIMENSIONS=64
PAPERVAULT_METADATA_LOCALE=en-IN
PAPERVAULT_DUPLICATE_CONTENT_SIMILARITY_THRESHOLD=0.88
PAPERVAULT_DUPLICATE_OCR_SIMILARITY_THRESHOLD=0.84
PAPERVAULT_DUPLICATE_SIMILARITY_MIN_TOKENS=24
```

These providers require no external credentials. The local analysis and answer
providers are deterministic baselines: they handle registry classification, structured
fields, concise summaries, and common labeled amount/date/list questions. Use a model
provider for richer free-form synthesis. Analysis, embeddings, and grounded answers
can use Ollama:

```env
PAPERVAULT_AI_PROVIDER=ollama
PAPERVAULT_ANSWER_PROVIDER=ollama
PAPERVAULT_EMBEDDING_PROVIDER=ollama
PAPERVAULT_EMBEDDING_DIMENSIONS=768
PAPERVAULT_OLLAMA_BASE_URL=http://host.docker.internal:11434
PAPERVAULT_OLLAMA_CHAT_MODEL=llama3.2
PAPERVAULT_OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

For an OpenAI-compatible endpoint, use `openai_compatible` for the three provider
values and configure `PAPERVAULT_OPENAI_COMPATIBLE_BASE_URL`, API key, chat model,
and embedding model. `PAPERVAULT_EMBEDDING_DIMENSIONS` must exactly match the
selected embedding model. Change the OpenSearch index name and rebuild the index
when changing embedding models or dimensions. Administrators can inspect active
provider reachability from Settings without exposing credentials.

`PAPERVAULT_METADATA_LOCALE` controls ambiguous numeric date parsing. `en-IN` and
other non-US values use day-first dates; `en-US` uses month-first dates. ISO dates
remain unambiguous for every locale.

Duplicate fingerprints are generated automatically for newly processed documents. Use
`POST /documents/duplicates/refresh` or the **Scan library** action to backfill existing
documents. Raising the similarity thresholds reduces false positives; lowering them
increases recall and should be paired with evaluation against the operator's OCR corpus.

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

The frontend stores the current bearer token in browser `localStorage` under `papervault.accessToken`. Development headers remain available only when:

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

OIDC login uses the provider authorization-code flow and exchanges the provider ID
token for PaperVault's own bearer token:

```env
OIDC_ISSUER_URL=https://idp.example.com/application/o/papervault/
OIDC_CLIENT_ID=papervault
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=http://localhost:8000/auth/oidc/callback
PAPERVAULT_WEB_APP_URL=http://localhost:5173
```

Register `OIDC_REDIRECT_URI` with the provider. For Gateway API deployments that
serve the API under `/api`, use `https://<host>/api/auth/oidc/callback`.

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
