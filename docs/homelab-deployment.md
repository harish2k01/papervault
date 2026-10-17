# Olympus deployment

PaperVault runs in the `papervault` namespace at
`https://papervault.k8s.harish2k01.xyz`, through the existing Traefik Gateway.

## Persistent services

`infra/k8s/homelab` defines:

- A CloudNativePG database with a 5 GiB Longhorn volume.
- Password-authenticated Redis with a 2 GiB Longhorn volume and AOF persistence.
- Digest-pinned RustFS S3 storage with a 20 GiB Longhorn volume. Its S3 service is
  private to the cluster and the console is disabled.
- Digest-pinned Ollama with a 15 GiB Longhorn model volume, a private ClusterIP,
  cloud inference disabled, and one CPU inference slot.

These are single-instance services. Longhorn replication does not provide an
independent database or object-store backup. Off-cluster backups and restore
verification remain required before treating the vault as the only copy of a file.

The application uses PostgreSQL-backed search for this initial deployment, matching
the primary exact-content retrieval workflow. OpenSearch indexing is disabled.
Analysis uses local Qwen3 1.7B with server-validated source references. Embeddings
and answers remain lexical baselines; this deployment does not provide model-based
semantic retrieval.

## Credentials

Credentials are generated at deployment and stored only in Kubernetes Secrets:

- `papervault-runtime`: database URL, authenticated Redis URL, object-store keys,
  and JWT signing key.
- `papervault-database-user`: the CloudNativePG application's username and password.
- `papervault-owner`: the bootstrap owner's `email` and `password`.

The initial owner is created privately before enabling the HTTPRoute. Open
registration and development identity headers remain disabled. An authorized cluster
operator can retrieve the bootstrap credentials from `papervault-owner`; they are
not committed to the repository or printed in deployment logs.

## Image identity and rollout

Resolve application images from a merged source revision:

```sh
python scripts/resolve_release_images.py --revision <full-git-commit>
```

The resolver verifies each Linux/amd64 image's OCI source revision before returning
the immutable manifest and platform digests. The Helm chart supports
`image.api.digest`, `image.worker.digest`, and `image.web.digest`. A configured
digest takes precedence over its tag.

The homelab profile refuses to render without verified image digests. Generate the
release lock separately and pass both files to Helm:

```sh
python scripts/resolve_release_images.py --revision <full-git-commit> --helm-values > release-images.json
helm upgrade --install papervault infra/helm/papervault --namespace papervault \
  -f infra/helm/papervault/values-homelab.yaml -f release-images.json --wait
```

Retain the lock with deployment records. It contains image identities, not credentials.

Dependency resources are installed independently:

```sh
kubectl --context admin@olympus apply -k infra/k8s/homelab
```

The application profile is `infra/helm/papervault/values-homelab.yaml`. Bootstrap
installation uses `migrations.useHelmHooks=false` because its ConfigMap and ServiceAccount
must exist before migrations can run. The HTTPRoute remains disabled until migrations,
the private documents bucket, and the owner account are ready. Later upgrades use
the chart's migration hook with the existing runtime resources.

The profile runs separate ingestion and enrichment consumers, each with concurrency
one and a prefetch multiplier of one. The ingestion consumer reads `celery`; the
enrichment consumer reads `papervault-enrichment`. Both use the verified worker image.
Image
builders use the runner network to avoid a nested Docker MTU mismatch.

## Local analysis model

The profile selects `qwen3:1.7b`, manifest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`.
On a fresh installation, provision these public weights before enabling the profile:

```sh
kubectl -n papervault rollout status statefulset/papervault-model
kubectl -n papervault exec papervault-model-0 -- ollama pull qwen3:1.7b
kubectl -n papervault exec papervault-model-0 -- ollama list
```

Verify the full manifest through `/api/tags`; the application rejects changed weights
before sending document text. Tags can move upstream, so a future download may require
a separately evaluated model update. Ollama has no ingress and `OLLAMA_NO_CLOUD=1`.
Document content travels only from the worker to this cluster service. Public model
downloads require internet access. Retain runtime and model identities with deployment
records independently of application releases.

The model pod requests 4 GiB, limits memory to 6 GiB and CPU to three cores, and uses
a 16,384-token context. Each source window has a conservative input budget plus
2,048 output tokens. Windows cover source pages instead of truncating a document at
a fixed character count. A 300-second request timeout surfaces failures for review.
Text becomes ready and searchable before enrichment is queued. Slow model analysis
therefore does not occupy the ingestion consumer or block OCR of later uploads.
`analysis_pending:metadata` remains visible until enrichment completes. Broker
publication or model failures become reviewable `analysis_failed:metadata` states
without removing extracted text. Each queued analysis is bound to an extraction ID;
Notification refresh failures are logged and do not stop enrichment publication.
obsolete and already completed deliveries skip model inference. Enrichment uses late
acknowledgement and requeues on worker loss through the existing persistent Redis.
Unexpected infrastructure exceptions use up to three retries with exponential
backoff; rejected model output remains a visible review failure rather than looping.

CPU analysis can still take minutes per page and remains serial on this hardware.
Queue separation improves ingestion availability, not model inference throughput.
The default chart keeps a single consumer for local installations; enable
`worker.separateEnrichment` to provision the second deployment. When disabling it,
the current worker image consumes both queues so outstanding enrichment can drain.
Before rolling back to an older image that lacks the enrichment task, drain the
enrichment queue or retain a compatible enrichment consumer until it is empty.

## Verification

A successful rollout requires more than a Helm `deployed` status:

- Database migrations are at Alembic head.
- Application container image IDs match the resolved platform digests.
- API and web readiness pass, and Celery responds through the configured Redis broker.
- The HTTPRoute is accepted and its service references resolve.
- The HTTPS route presents a trusted certificate and loads the Cobalt web build.
- An authenticated synthetic upload completes through real storage and the worker;
  its content is searchable and its downloaded original matches byte-for-byte.
- Scanned images and mixed PDFs exercise real Tesseract extraction.
- Unauthenticated and cross-account document access are rejected.

Synthetic verification accounts and documents are removed after the checks.
