# ADR 0014: OIDC Browser Login Boundary

## Status

Accepted

## Context

PaperVault needs to support self-hosted identity providers such as Authentik and
Keycloak while still issuing its own API bearer tokens. The web application should
not store OIDC client secrets or exchange authorization codes directly.

## Decision

PaperVault implements OIDC authorization-code login in the API:

- The frontend redirects users to `GET /auth/oidc/start`.
- The API creates a signed, expiring state token containing a nonce and same-origin
  post-login redirect path.
- The API discovers the provider, builds the authorization URL, exchanges the
  callback code, verifies the ID token through provider JWKS, and creates or updates
  the PaperVault user.
- The callback redirects to the web app with a PaperVault bearer token in the URL
  fragment.
- Existing local accounts are not automatically linked to OIDC accounts by email.

## Consequences

OIDC provider credentials remain server-side, and the frontend continues to use one
PaperVault bearer-token model. The flow is stateless across API replicas because
state is signed rather than stored in process memory. Operators must configure the
exact callback URI, especially when the API is served behind a `/api` route prefix.
