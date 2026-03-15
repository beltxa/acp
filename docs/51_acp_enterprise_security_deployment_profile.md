# ACP Enterprise Security Deployment Profile

Version: Draft v1
Date: 2026-03-15

## Purpose

Define one coherent ACP enterprise deployment profile that combines:

- HTTPS-first transport policy
- optional HTTP mTLS profile
- Vault-backed key custody via key-provider abstraction

This profile does not change ACP core protocol semantics.

## Profile Model

### Required baseline

- `allow_insecure_http = false`
- `allow_insecure_tls = false`
- HTTP-based ACP endpoints and relay URLs use `https://`
- key custody uses provider abstraction (`local` or `vault`)

### Optional hardening

- `mtls_enabled = true`
- client certificate and key are provided either:
  - directly (`cert_file`, `key_file`), or
  - by key provider (Vault-backed runtime material)

### Local/dev exception model

- `http://` is only allowed via explicit override:
  - `allow_insecure_http = true`
- insecure TLS is only allowed via explicit override:
  - `allow_insecure_tls = true`

## Agent Identity vs Endpoint Trust

ACP identity and transport endpoint trust remain separate:

- ACP identity: logical agent continuity, signatures, message encryption identity.
- Endpoint trust: HTTPS certificate validation and optional mTLS endpoint authentication.
- Key custody: where signing/encryption/TLS material is stored and retrieved (`local` or `vault`).

This follows the ACP trust separation model in `48_acp_agent_identity_vs_endpoint_trust_model.md`.

## Key Provider Configuration Surface

Common settings:

- `key_provider`: `local` or `vault`
- `ca_file`
- `mtls_enabled`
- `cert_file`
- `key_file`

Vault settings:

- `vault_url`
- `vault_path`
- `vault_token_env`
- optional explicit token wiring in runtime configuration

Python CLI config and Java `AcpAgentOptions.fromConfigMap(...)` use the same field names for this profile.

## Vault Secret Structure (v1)

Identity keys:

- `signing_key`
- `encryption_key`
- optional: `signing_public_key`, `encryption_public_key`, `signing_kid`, `encryption_kid`

TLS/trust material:

- `ca_file` (or `ca_bundle_file`)
- `tls_cert_file`
- `tls_key_file`

## Reference Config Examples

### 1. Local provider + HTTPS

```yaml
key_provider: local
allow_insecure_http: false
allow_insecure_tls: false
mtls_enabled: false
ca_file: /etc/ssl/certs/enterprise-ca.pem
```

### 2. Vault provider + HTTPS

```yaml
key_provider: vault
vault_url: https://vault.example.net
vault_path: secret/data/acp/identities
vault_token_env: VAULT_TOKEN
allow_insecure_http: false
allow_insecure_tls: false
mtls_enabled: false
ca_file: /etc/ssl/certs/enterprise-ca.pem
```

### 3. Vault provider + HTTPS + mTLS

```yaml
key_provider: vault
vault_url: https://vault.example.net
vault_path: secret/data/acp/identities
vault_token_env: VAULT_TOKEN
allow_insecure_http: false
allow_insecure_tls: false
mtls_enabled: true
# cert/key may be supplied by Vault provider material or explicit file settings.
```

## Operator Visibility

Operators should check:

- active key provider and safe source metadata (`provider`, `vault_url`, `vault_path`)
- HTTPS/mTLS profile state
- insecure override flags

Current visibility points:

- `acp config show`
- `acp config validate`
- `acp identity show`
- `acp agent status`
- `acp relay status`

## Out of Scope for This Profile

- cloud KMS providers (AWS/Azure/GCP)
- token lifecycle automation
- rotation orchestration
- certificate issuance/revocation pipelines
- mTLS for non-HTTP transports
