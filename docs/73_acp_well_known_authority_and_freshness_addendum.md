# ACP Well-Known Authority and Freshness Addendum
Version: Draft v1

## Purpose
Clarifies authority, precedence, and caching behavior for the ACP well-known endpoint:

`/.well-known/acp`

The endpoint is a bootstrap discovery mechanism, not a trust root.

---

## Authority Model

Clients must validate:
1. TLS endpoint trust
2. ACP identity document signatures
3. ACP message signatures

Well-known metadata is advisory and should not be treated as a primary trust source.

---

## Field Authority

### Authoritative bootstrap fields
- `agent_id`
- `identity_document`
- `version`

### Advisory operational hints
- `transports`
- `security_profile`
- `relay_hint`
- `capabilities`
- `metadata`

---

## Cache Behavior

Recommended behavior:

- Honor HTTP cache headers when present
- Default TTL: **300 seconds**
- Framework overlay wrappers should emit `Cache-Control: public, max-age=300` on `/.well-known/acp`
- Refresh metadata when:
  - transport failure occurs
  - identity verification fails
  - endpoint migration is suspected

---

## Conflict Resolution

Priority order:

1. Local configuration
2. Enterprise discovery registry
3. Well-known endpoint
4. Cached metadata

---

## Security Rules

The well-known endpoint must never expose:

- private keys
- secrets
- tokens
- internal configuration values

Only public metadata should be returned.

---

## Summary

Well-known discovery provides bootstrap metadata while trust remains anchored in:

- TLS endpoint validation
- ACP identity verification
- ACP message signatures
