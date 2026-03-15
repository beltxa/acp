# ACP HTTP mTLS Profile Implementation Results

Date: 2026-03-15

## Scope

This pass implements the optional ACP HTTP mTLS transport profile for:

- ACP Python SDK HTTP client paths
- ACP Java SDK HTTP client paths
- ACP Python relay HTTP client paths and relay HTTPS listener startup configuration
- ACP CLI/config validation and operational visibility

ACP core protocol semantics are unchanged.

## Defaults

- `mtls_enabled = false` (optional enterprise profile)
- `allow_insecure_http = false`
- `allow_insecure_tls = false`
- TLS verification remains enabled by default

## Settings

- `mtls_enabled`
- `ca_file`
- `cert_file`
- `key_file`
- existing HTTPS hardening settings remain:
  - `allow_insecure_http`
  - `allow_insecure_tls`

## Behavior

- HTTP paths are HTTPS-first.
- mTLS-enabled HTTP paths require client certificate material (`cert_file` + `key_file`).
- `ca_file` is used for custom trust roots when TLS verification is enabled.
- If `mtls_enabled=true`, HTTP (`http://`) transport paths are rejected.
- Discovery/registration identity service hints can carry `security_profile: "mtls"` under `service.http` and `service.relay`.

## Intentional Local/Dev Exceptions

- Local/demo `http://` remains available only when explicit insecure override is set.
- Local/self-signed mTLS remains supported through explicit local CA/cert/key settings.

## Remaining Enterprise Gaps (Out of Scope)

- certificate issuance/rotation automation
- revocation and PKI lifecycle management
- certificate pinning framework
- mTLS for non-HTTP transports
