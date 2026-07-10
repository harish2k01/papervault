# ADR 0023: Persisted Instance Policy

## Status

Accepted

## Context

Environment variables are appropriate for secrets and deployment topology, but requiring a Helm or container restart to close local registration is unnecessarily operational. Administrators also need one place to manage users and see which non-secret providers are active.

## Decision

Keep deployment configuration as the bootstrap default and store explicit administrator overrides in a singleton `instance_settings` row. Apply the effective registration policy to public auth discovery and local registration requests.

Expose admin-only settings endpoints and a Settings workspace. User roles and active state continue to use the identity service and existing last-active-administrator protections. Provider names and capability flags are read-only; credentials remain outside PostgreSQL.

## Consequences

- Registration can be changed without restarting workloads.
- A fresh installation behaves according to environment configuration until an administrator saves an override.
- Runtime policy is durable across pod replacement.
- Additional mutable settings must be added as typed columns and reviewed individually rather than becoming an unrestricted key/value store.
