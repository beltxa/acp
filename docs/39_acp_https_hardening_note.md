# ACP HTTPS Hardening Note

Version: Draft v1

## Purpose

This document defines the HTTPS hardening direction for ACP HTTP-based transport paths.

ACP already provides protocol-layer payload encryption, but HTTP transport paths should use HTTPS by default in all non-local environments.

This hardening improves:

- security review acceptance
- endpoint authenticity
- protection of transport metadata
- operational credibility
- deployment readiness

This change does not alter ACP core semantics.

---

## 1. Core Rule

For all HTTP-based ACP transports:

- HTTPS should be the default
- plain HTTP should be allowed only for:
  - local development
  - controlled demos
  - explicitly configured insecure mode

ACP payload security remains enforced at the protocol layer.

HTTPS adds transport-layer protections and aligns ACP with common security expectations.

---

## 2. Scope

This hardening applies to:

- direct agent HTTP endpoints
- relay HTTP endpoints
- discovery endpoints using HTTP(S)
- registration endpoints using HTTP(S)
- demo and sample configurations
- CLI/config validation behavior

This hardening does not change:

- ACP identity model
- ACP message model
- ACP encryption model
- ACP relay semantics
- ACP discovery semantics

---

## 3. Transport Policy

Recommended runtime policy:

- `allow_insecure_http = false` by default
- `allow_insecure_http = true` only for local/dev/demo use
- emit a clear warning when insecure HTTP is enabled

Example policy behavior:

- production endpoint with `http://` → reject unless explicitly allowed
- local endpoint with `http://localhost` → allowed in dev mode
- demo endpoint with `http://<temporary-host>` → allowed only with explicit override

---

## 4. Discovery and Registration Hints

HTTP service hints should prefer `https://` endpoints.

Example:

```json
{
  "service": {
    "http": {
      "endpoint": "https://agent.example.com/acp"
    }
  }
}
```

Relay hints should also prefer HTTPS.

Example:

```json
{
  "service": {
    "relay": {
      "endpoint": "https://relay.example.com"
    }
  }
}
```

All documentation and examples should prefer HTTPS by default.

---

## 5. Certificate Expectations

For production-like environments, ACP HTTP clients should:

- validate server certificates
- validate hostname matching
- reject invalid or expired certificates unless explicitly overridden

For local development and demos, ACP may support:

- self-signed certificates
- local CA trust
- explicit insecure override

Recommended local/dev options:

- `--allow-insecure-http`
- `--allow-insecure-tls`
- `--ca-file <path>`

These flags must be explicit and visible.

---

## 6. CLI and Config Behavior

CLI and config validation should:

- warn or reject insecure HTTP endpoints by default
- allow explicit insecure mode for local/demo workflows
- clearly show whether an endpoint is using:
  - HTTPS
  - insecure HTTP
  - insecure TLS mode

Config validation should detect:

- `http://` direct agent endpoints
- `http://` relay endpoints
- insecure discovery URLs

---

## 7. Demo Guidance

For the John demo and similar demos:

- HTTPS is preferred if practical
- temporary HTTP can still be used if clearly marked as demo-only
- if HTTP is used, docs and CLI should show that it is an explicit exception

Recommended demo language:

> ACP secures the payload at the protocol layer, but production deployments use HTTPS by default for transport as well.

---

## 8. Future Hardening

Possible future enhancements:

- optional mTLS for enterprise deployments
- certificate pinning profiles
- enterprise trust-store integration
- stricter transport security policy profiles

These should be treated as optional hardening layers, not mandatory ACP core behavior.

---

## 9. Recommended Documentation Changes

Update the following materials to prefer HTTPS:

- quick start
- protocol summary
- transport support examples
- relay config examples
- agent config examples
- demo kit configs
- discovery/registration examples

---

## 10. Summary

ACP does not need a protocol redesign to use HTTPS.

The correct direction is:

- keep ACP protocol-layer encryption
- make HTTPS the default for HTTP transport paths
- allow insecure HTTP only by explicit local/dev/demo exception
- update configs, docs, CLI validation, and examples accordingly
