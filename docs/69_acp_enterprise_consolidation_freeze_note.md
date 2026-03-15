# ACP Enterprise Consolidation Freeze Note

Date: 2026-03-15  
Status: Frozen for current enterprise security profile

## 1. Enterprise Profile Baseline

The current enterprise profile is frozen as:

- HTTPS-first for HTTP-based ACP paths
- optional HTTP mTLS profile
- key-provider abstraction for key/TLS custody
- `local` and `vault` providers as current supported set
- explicit insecure overrides only (`allow_insecure_http`, `allow_insecure_tls`)

## 2. Canonical Config Field Set

Canonical security/provider fields:

- `key_provider`
- `vault_url`
- `vault_path`
- `vault_token_env`
- `mtls_enabled`
- `ca_file`
- `cert_file`
- `key_file`
- `allow_insecure_http`
- `allow_insecure_tls`

## 3. Python / Java / Relay Parity

Python SDK:

- supports canonical field set
- provider-backed identity keys + TLS material
- HTTPS/mTLS validation and enforcement in runtime paths

Java SDK:

- supports canonical field set via `AcpAgentOptions`
- provider-backed identity keys + TLS material
- HTTPS/mTLS enforcement and trust-store/client-cert support in HTTP client
- normalized defaults aligned (`key_provider=local`, `vault_token_env=VAULT_TOKEN`)

Relay:

- environment/config uses the same canonical security/provider fields
- supports local/vault provider-backed TLS material
- surfaces secure profile metadata through status/routing snapshots

## 4. Canonical Example Set (Frozen)

Frozen reference examples:

- `examples/enterprise/local-provider-https.yaml`
- `examples/enterprise/vault-provider-https.yaml`
- `examples/enterprise/vault-provider-https-mtls.yaml`

## 5. Validation / Testing State

Cross-language/enterprise profile checks currently covered by:

- `acp-sdk-python/tests/test_enterprise_profile_compat.py`
- `acp-sdk-python/tests/test_cli_key_provider.py`
- `acp-sdk-java/src/test/java/org/acp/client/EnterpriseProfileConfigCompatibilityTest.java`
- `acp-sdk-java/src/test/java/org/acp/client/VaultKeyProviderTest.java`
- `acp-sdk-java/src/test/java/org/acp/client/HttpSecurityMtlsTest.java`
- `acp-relay/tests/test_key_provider.py`
- `acp-relay/tests/test_https_mtls.py`

## 6. Remaining Known Gaps (Intentionally Deferred)

- AWS KMS / other cloud-provider key providers
- rotation automation / PKI lifecycle tooling
- certificate revocation/issuance orchestration
- non-HTTP enterprise transport hardening extensions
