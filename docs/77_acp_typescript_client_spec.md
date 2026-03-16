# ACP TypeScript Client Specification

## 1. Purpose

This document defines the implemented scope of the internal TypeScript SDK package:

- `acp-sdk-typescript`

The SDK is intended for Node.js/TypeScript ACP clients and aligns with the current Python, Java, and Rust ACP SDK behavior model.

## 2. Package status

- Internal only (`private: true`, `UNLICENSED`)
- Runtime target: Node.js (ES2022, ESM)
- Validated by:
  - `npm run lint`
  - `npm run test`
  - `npm run build`

## 3. Implemented module surface

Core protocol/runtime:

- `messages` (typed ACP envelope/protected/message models)
- `jsonSupport` (canonical JSON)
- `crypto` (Ed25519 signatures, X25519 key agreement, AES-256-GCM payload/wrap encryption)
- `identity` (identity generation, identity document build/sign/verify, local storage)
- `capabilities` (compatibility negotiation helpers)
- `agent` (send/receive, dedup, terminal ACK/FAIL behavior, capability request)

Discovery and transport:

- `wellKnown` (`/.well-known/acp` build/parse/validation)
- `discovery` (cache, well-known lookup, relay/directory hint lookup)
- `transport` (direct HTTP + relay HTTP send paths)
- `amqpTransport` (publish/consume, stable routing key and header mapping)
- `mqttTransport` (publish/consume, stable topic and user-property mapping)

Security and key custody:

- `httpSecurity` (HTTPS-first validation, explicit insecure override, mTLS file checks)
- `keyProvider` (`KeyProvider`, `LocalKeyProvider`, `VaultKeyProvider`)

Overlay adoption:

- `overlay` (thin inbound/outbound overlay adapters)
- `overlayFramework` (framework runtime helpers and outbound overlay client)

## 4. ACP behavior invariants preserved

- ACP message payload remains canonical transport body.
- At-least-once delivery assumption is preserved.
- Duplicate handling is recipient-side via `message_id` dedup.
- ACK and FAIL are terminal protocol responses.
- No ACK-of-ACK or FAIL-of-FAIL loops.
- For AMQP/MQTT delivery, per-recipient publish uses single-recipient ACP envelope.
- Well-known metadata is advisory; signed identity document verification is authoritative.

## 5. Shared-vector parity tests

TypeScript tests validate the same shared fixtures used by other SDKs:

- `tests/vectors/amqp/*`
- `tests/vectors/mqtt/*`
- `tests/vectors/security/*`
- `tests/vectors/well_known/*`

Implemented test coverage includes:

- AMQP fixture conformance and metadata stability
- MQTT fixture conformance and topic/property stability
- enterprise config compatibility vectors
- well-known valid/invalid fixture validation
- crypto sign/encrypt/decrypt roundtrip
- overlay bootstrap via `.well-known/acp`

## 6. Configuration fields supported

Implemented config model includes:

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
- `vault_token` (optional direct token)

Transport-specific fields:

- `amqp_broker_url`, `amqp_exchange`, `amqp_exchange_type`
- `mqtt_broker_url`, `mqtt_qos`, `mqtt_topic_prefix`

## 7. Out of scope (this pass)

- Cloud KMS providers beyond Vault
- cert issuance, rotation automation, revocation automation
- non-HTTP overlay adapters
- relay MQTT fallback
- exactly-once transport semantics
