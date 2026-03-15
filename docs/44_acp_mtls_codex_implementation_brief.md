# ACP HTTP mTLS Profile Codex Implementation Brief

## Purpose

Implement the optional ACP HTTP mTLS Profile for HTTP-based ACP transport paths.

This is an enterprise transport hardening pass.

It must not redesign ACP core semantics.

ACP already has:
- protocol-layer encryption
- HTTPS-first behavior
- explicit insecure overrides for local/dev/demo

This pass adds optional mutual TLS support for environments that require transport-layer authentication of both client and server.

---

## Objective

Add optional mTLS support to ACP HTTP-based transport paths so that enterprise deployments can enable:

- server certificate validation
- client certificate presentation
- private CA / trust-store usage
- relay endpoint mutual authentication where applicable

This support should be available but not required by default.

---

## Important Rules

1. Do not redesign ACP identity, discovery, message, or encryption models.
2. Do not make mTLS mandatory for ACP core.
3. Treat mTLS as an optional enterprise HTTP transport profile.
4. Keep insecure local/dev/demo modes available where explicitly configured.
5. Keep implementation small and practical.
6. Do not build enterprise PKI lifecycle tooling.
7. Do not implement mTLS for AMQP/MQTT/Kafka/JMS/P2P in this pass.

---

## Required Scope

### 1. Config / Settings

Implement the smallest clean config/settings surface needed, such as:

- `mtls_enabled` (default false)
- `ca_file`
- `cert_file`
- `key_file`

Retain existing HTTPS hardening settings where applicable:
- `allow_insecure_http`
- `allow_insecure_tls`

Expected behavior:
- if `mtls_enabled = true`, client/server configs must validate presence of required certificate material where appropriate
- invalid combinations should fail fast in validation

---

## 2. Python SDK

Update Python HTTP transport paths to support optional mTLS:

- HTTPS client can load CA trust from `ca_file`
- HTTPS client can present client cert and key from `cert_file` and `key_file`
- validation remains strict by default
- connection should fail clearly if mTLS is enabled but cert config is missing/broken

Where practical, align direct HTTP and relay-facing HTTP client behavior.

---

## 3. Java SDK

Close the existing Java HTTPS trust gap and extend it for the optional mTLS profile:

- wire `caFile` into Java trust-store handling
- support client certificate and key for HTTP client path if practical in the same pass
- if full Java client-cert support is too large for one pass, implement trust-store support first and clearly report what remains

Keep implementation minimal and realistic.

---

## 4. Python Relay

Add optional mTLS support to the relay’s HTTP-facing path:

- relay listener can be configured for HTTPS + optional client cert requirement
- relay client-side HTTP calls can use trust/cert settings where relevant
- relay must still remain payload-blind with respect to ACP message contents

Do not add a full ingress/cert automation framework.

---

## 5. Discovery / Registration Hints

Support optional transport hints indicating the mTLS profile for HTTP endpoints.

Use existing hint shapes where possible, for example:
- `security_profile: "mtls"`

Do not redesign the discovery schema.

---

## 6. CLI / Validation

Update CLI/config validation to:

- validate `mtls_enabled` combinations
- require `cert_file` and `key_file` when appropriate
- surface whether endpoints are:
  - HTTPS only
  - HTTPS + mTLS
  - insecure override

Useful commands include:
- config validate
- transport probe
- agent status
- relay status

Keep this visible but not noisy.

---

## 7. Tests

Add or update focused tests for:

### Python
- HTTPS + CA trust handling
- mTLS-enabled config validation
- missing cert/key failure paths
- client certificate use where testable

### Java
- custom CA trust-store wiring
- mTLS-related config validation
- any client-cert support implemented in this pass

### Relay
- HTTPS listener with mTLS-enabled config validation
- operator-visible status output for secure profile

Keep tests practical and lightweight.

---

## 8. Documentation Deliverables

Update or create the minimum necessary docs:

1. mTLS profile specification reflected in docs/examples
2. config examples for HTTPS + mTLS
3. note on local/dev self-signed usage
4. clear statement that mTLS is optional enterprise profile, not ACP core requirement

---

## 9. Out of Scope

Do not implement:
- enterprise CA enrollment
- automated certificate issuance
- revocation management
- pinning framework
- mTLS for AMQP/MQTT/Kafka/JMS/P2P
- enterprise secrets platform integration
- full production ingress automation

---

## 10. Working Rule

Implement the smallest clean optional mTLS profile that materially strengthens ACP’s enterprise HTTP transport story without increasing core adoption friction.

If a gap remains — especially on the Java side — report it explicitly rather than expanding scope uncontrollably.
