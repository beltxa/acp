# Vector Scope Classification

This file classifies vector families under `sdks/tests/vectors/` for public parity claims.

## Classification Summary

| Family | Classification | Public parity claim scope | Notes |
| --- | --- | --- | --- |
| `amqp/` | `authoritative public` | Included | Frozen transport fixtures for protocol carriage semantics. |
| `mqtt/` | `authoritative public` | Included | Frozen transport fixtures for protocol carriage semantics. |
| `well_known/` | `authoritative public` | Included | Discovery and well-known validation contract vectors. |
| `security/` | `internal-only` | Excluded | Kept for SDK compatibility regression; not part of public parity claims. |

## Sanitization Decision

The `security/` vectors contain private-scope profile naming and infrastructure placeholders. To avoid unnecessary public leakage in parity framing:

- they remain available for internal SDK compatibility checks
- they are marked `internal-only` in the vector manifest
- they are excluded from public parity/interoperability proof claims

Security fixture names have been normalized to public-safe identifiers.

## Contract Boundary

Public contract parity for release claims is based on:

- `amqp/`
- `mqtt/`
- `well_known/`

`security/` vectors do not increase public parity claims in this repository model.
