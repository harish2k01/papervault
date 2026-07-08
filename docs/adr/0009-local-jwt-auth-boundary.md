# ADR 0009: Add Local JWT Authentication Before OIDC

## Status

Accepted

## Context

PaperVault needs OIDC, local login, JWTs, and RBAC. Earlier phases used development identity headers so document ownership and API workflows could be built without blocking on identity provider integration. That boundary is not acceptable for production deployments.

## Decision

Phase 6 adds a local authentication boundary:

- local registration and login endpoints
- first-user administrator bootstrap
- password hashes stored on `users` for local accounts
- signed bearer tokens with issuer, audience, expiry, and role claims
- reusable current-user and role-check dependencies
- admin-only user listing and updates
- frontend authentication screen and token storage
- explicit development-header fallback disabled automatically in production

OIDC settings remain configured but OIDC login is deferred.

## Consequences

Self-hosted users can now run PaperVault without an external identity provider. The trade-off is that refresh tokens, session revocation, MFA, and OIDC federation still need later phases. Production deployments must replace `JWT_SIGNING_KEY`, disable development headers, and close local registration after bootstrapping the administrator.
