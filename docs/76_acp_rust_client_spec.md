# ACP Rust Client Specification

## 1. Purpose

This document captures the implemented behavior of the internal Rust SDK package:

- `acp-sdk-rust`

The SDK is an ACP protocol client/runtime library for Rust applications and is aligned with the current ACP implementation baseline used by Python and Java SDKs.

## 2. Package status

- Internal only (`publish = false`, `UNLICENSED`)
- Rust edition: 2024
- Verified with `cargo check` and `cargo test`

## 3. Implemented modules

Core:

- `messages` (envelope/protected payload/message model)
- `json_support` (canonical JSON normalization)
- `crypto` (Ed25519, X25519, AES-256-GCM, signature and decrypt/verify flow)
- `identity` (identity creation, identity document signing/verification, local read/write)
- `capabilities` (compatibility matching)
- `agent` (send/receive, dedup, ACK/FAIL terminal behavior, capability request)

Transport/discovery:

- `transport` (direct HTTP send, relay send)
- `discovery` (cache, `.well-known`, relay/directory hint lookup)
- `well_known` (`/.well-known/acp` generation/validation/reference resolution)
- `amqp_transport` (publish/consume and metadata mapping)
- `mqtt_transport` (publish/consume and metadata mapping)

Security/enterprise:

- `http_security` (HTTPS-first policy, insecure override control, mTLS file validation)
- `key_provider` (`KeyProvider`, `LocalKeyProvider`, `VaultKeyProvider`)

Overlay:

- `overlay` (inbound/outbound overlay adapters)
- `overlay_framework` (runtime helpers, cache-control constants, overlay client)

## 4. Protocol behavior requirements implemented

- ACP message body remains canonical across transport bindings.
- At-least-once delivery assumptions preserved.
- Recipient dedup behavior by `message_id`.
- ACK/FAIL treated as terminal (no ACK-of-ACK/FAIL-of-FAIL loops).
- Multi-recipient AMQP/MQTT send split to single-recipient envelopes on publish paths.
- Discovery uses `.well-known` metadata as advisory input; identity document verification remains authoritative.

## 5. Interoperability and parity artifacts

Rust test suite validates shared ACP vectors:

- `tests/vectors/amqp/*`
- `tests/vectors/mqtt/*`
- `tests/vectors/security/*`
- `tests/vectors/well_known/*`

Rust tests include:

- AMQP fixture conformance
- MQTT fixture conformance
- enterprise profile config compatibility
- well-known fixture parsing/validation
- crypto roundtrip
- overlay runtime/bootstrap flow

## 6. Runtime configuration shape

Implemented key runtime/config fields include:

- `allow_insecure_http`
- `allow_insecure_tls`
- `mtls_enabled`
- `ca_file`
- `cert_file`
- `key_file`
- `key_provider` (`local` / `vault`)
- `vault_url`
- `vault_path`
- `vault_token_env`

## 7. Out of scope (not implemented in Rust SDK)

- Cloud KMS providers beyond Vault
- PKI lifecycle automation / rotation / revocation
- Relay MQTT fallback path
- Non-HTTP overlay adapters
- Sender descriptor envelope extension
