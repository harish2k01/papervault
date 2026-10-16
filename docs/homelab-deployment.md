# Olympus deployment

PaperVault runs in the `papervault` namespace at
`https://papervault.k8s.harish2k01.xyz`, through the existing Traefik Gateway.

## Persistent services

`infra/k8s/homelab` defines:

- A CloudNativePG database with a 5 GiB Longhorn volume.
- Password-authenticated Redis with a 2 GiB Longhorn volume and AOF persistence.
- Digest-pinned RustFS S3 storage with a 20 GiB Longhorn volume. Its S3 service is
  private to the cluster and the console is disabled.

These are single-instance services. Longhorn replication does not provide an
independent database or object-store backup. Off-cluster backups and restore
verification remain required before treating the vault as the only copy of a file.

The application uses PostgreSQL-backed search for this initial deployment, matching
the primary exact-content retrieval workflow. OpenSearch indexing is disabled.
The built-in local analysis and hashing embedding providers remain lexical baselines;
the deployment does not claim model-level semantic understanding.

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

Dependency resources are installed independently:

```sh
kubectl --context admin@olympus apply -k infra/k8s/homelab
```

The application profile is `infra/helm/papervault/values-homelab.yaml`. Bootstrap
installation uses `migrations.useHelmHooks=false` because its ConfigMap and ServiceAccount
must exist before migrations can run. The HTTPRoute remains disabled until migrations,
the private documents bucket, and the owner account are ready. Later upgrades use
the chart's migration hook with the existing runtime resources.

Workers have explicit concurrency of two and a prefetch multiplier of one. Image
builders use the runner network to avoid a nested Docker MTU mismatch.

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
