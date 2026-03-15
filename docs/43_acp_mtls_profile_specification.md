# ACP HTTP Transport mTLS Profile Specification

Version: Draft v1

## 1. Purpose

This document defines the optional mTLS transport profile for ACP over HTTP(S).

ACP core already provides:

- protocol-layer payload encryption
- HTTPS-first transport hardening
- server certificate validation by default

This profile adds mutual TLS (mTLS) for environments that require transport-layer authentication of both client and server.

This profile is intended primarily for:

- enterprise deployments
- regulated environments
- private partner networks
- high-assurance internal ACP deployments

This profile is optional and does not change ACP core semantics.

---

## 2. Profile Positioning

ACP security should be understood as layered:

### ACP Core
- protocol-layer encryption
- HTTPS by default
- optional insecure local/dev exceptions

### ACP HTTP mTLS Profile
- server certificate validation
- client certificate presentation
- mutual TLS authentication
- private CA / trust-store support

### Future Enterprise Hardening
- certificate rotation automation
- enterprise PKI integration
- certificate pinning
- policy-driven transport security

The mTLS profile belongs to the second layer.

---

## 3. Scope

This profile applies only to HTTP-based ACP transport paths:

- direct agent HTTP endpoints
- relay HTTP endpoints
- discovery/registration HTTP endpoints where applicable

This profile does not currently define mTLS behavior for:

- AMQP
- MQTT
- Kafka
- JMS
- P2P

---

## 4. Core Rule

When the ACP HTTP mTLS profile is enabled:

- HTTP-based ACP clients must present a client certificate
- HTTP-based ACP servers/relays must validate client certificates according to configured trust rules
- server certificate validation remains mandatory
- ACP payload encryption remains unchanged and still required

mTLS augments ACP transport security; it does not replace protocol-layer security.

---

## 5. Configuration Model

Recommended configuration concepts:

- `mtls_enabled` (bool, default false)
- `ca_file` (optional trust store / CA bundle)
- `cert_file` (client/server certificate)
- `key_file` (client/server private key)
- `allow_insecure_tls` (default false; should not be used in mTLS mode except explicit local dev)

Recommended rule:
- if `mtls_enabled = true`, both `cert_file` and `key_file` must be supplied for the endpoint acting as TLS client
- servers/relays must be configured to request/require client certificates where the profile is enforced

---

## 6. Discovery and Registration Hints

The mTLS profile does not require a new ACP identity or discovery model.

Transport hints may optionally indicate that an endpoint expects the mTLS profile.

Example:

```json
{
  "service": {
    "http": {
      "endpoint": "https://agent.example.com/acp",
      "security_profile": "mtls"
    }
  }
}
```

or:

```json
{
  "service": {
    "relay": {
      "endpoint": "https://relay.example.com",
      "security_profile": "mtls"
    }
  }
}
```

This is a transport hint, not a trust root.

ACP identity is still asserted through ACP identity documents and message signatures.

---

## 7. Trust Model

mTLS provides transport-layer authentication of the endpoint connection.

ACP still requires:
- ACP identity verification
- message signature verification
- protocol-layer payload encryption

Therefore:

- mTLS does not replace ACP identity
- ACP identity does not replace mTLS where mTLS is required
- both may operate together

This layering is important for enterprise review.

---

## 8. Client Behavior

When mTLS profile is enabled for an HTTP target:

ACP client must:
- connect using HTTPS
- validate server certificate
- present configured client certificate and key
- use configured CA trust if provided
- reject the connection if mTLS requirements cannot be satisfied

ACP client should clearly surface configuration errors such as:
- missing cert file
- missing key file
- invalid CA file
- failed certificate validation

---

## 9. Server / Relay Behavior

When the mTLS profile is enabled on an ACP HTTP listener:

ACP server or relay should:
- require or explicitly request client certificates
- validate presented certificates according to configured trust rules
- reject connections that do not satisfy mTLS policy
- continue to process ACP payloads normally after transport authentication succeeds

The relay must still not decrypt ACP payloads unless explicitly part of an ACP endpoint role.

---

## 10. CLI / Validation Behavior

CLI and config validation should support this profile by:

- surfacing whether `mtls_enabled` is active
- validating that required files are present
- warning if `allow_insecure_tls` is set in mTLS mode
- showing whether a given endpoint is:
  - HTTPS only
  - HTTPS + mTLS
  - insecure local/dev override

This helps both operators and auditors.

---

## 11. Recommended v1 Scope

The first implementation of the mTLS profile should support:

- Python SDK HTTP client/server paths
- Java SDK HTTP client path
- Python relay HTTP listener/client path
- CA trust-store support
- client certificate and key loading
- config validation and basic operational visibility

The first implementation should not attempt:

- automated certificate issuance
- enterprise PKI enrollment
- rotation automation
- certificate revocation management
- certificate pinning framework

---

## 12. Demo and Local Development

mTLS can be difficult in early demos.

Recommended approach:

- keep mTLS available but optional
- support local CA or self-signed development certificates
- do not make mTLS mandatory for local/demo flows
- keep `allow_insecure_http` / `allow_insecure_tls` explicit and clearly non-production

---

## 13. Security Positioning

ACP with HTTPS-first + optional mTLS profile can be positioned as:

- protocol-layer secure by design
- transport-layer secure by default
- enterprise-hardenable where mutual authentication is required

This is a stronger and more realistic enterprise story than relying on payload encryption alone.

---

## 14. Summary

The ACP HTTP mTLS profile is an optional enterprise transport profile that adds mutual TLS authentication to HTTP-based ACP transport paths without changing ACP core semantics.

It should be implemented as a configurable hardening layer, not a mandatory ACP-wide requirement.
