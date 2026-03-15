# ACP Enterprise Profile Consolidation Results

Date: 2026-03-15

## Final Agreed Config Fields

Enterprise profile field set:

- `key_provider`
- `vault_url`
- `vault_path`
- `vault_token_env`
- `allow_insecure_http`
- `allow_insecure_tls`
- `mtls_enabled`
- `ca_file`
- `cert_file`
- `key_file`

## Python / Java Differences

### Aligned

- Python and Java support `local` and `vault` providers.
- Python and Java both use provider-resolved TLS/CA material for HTTPS/mTLS runtime behavior.
- Python and Java both enforce HTTPS-first with explicit insecure overrides.

### Practical differences

- Python uses CLI/config file loading directly with these fields.
- Java primary runtime API remains typed setters (`setKeyProvider`, `setVaultUrl`, etc.), but now also supports `AcpAgentOptions.fromConfigMap(...)` with the same snake_case field names for parity.
- Java does not include a built-in CLI/config file loader in this pass.

## Relay Alignment Status

Relay is aligned with the enterprise profile:

- HTTPS-first behavior retained.
- Optional mTLS retained.
- `key_provider` support added (`local`/`vault`) for TLS/CA material.
- Relay status now surfaces safe key-provider metadata via routing snapshot.
- Insecure HTTP/TLS overrides remain explicit and visible.

## Examples Added

- `examples/enterprise/local-provider-https.yaml`
- `examples/enterprise/vault-provider-https.yaml`
- `examples/enterprise/vault-provider-https-mtls.yaml`

Shared config compatibility vectors added:

- `tests/vectors/security/enterprise_profile_https.json`
- `tests/vectors/security/enterprise_profile_vault_mtls.json`

## Validation and Test Results

Executed:

- `PYTHONPATH=acp-sdk-python pytest -q acp-sdk-python/tests`
- `mvn -q test` (in `acp-sdk-java`)
- `pytest -q acp-relay/tests`

All passed in this consolidation pass.

## Remaining Gaps Before AWS KMS

- No AWS/Azure/GCP provider implementations yet.
- No token lifecycle automation.
- No key/cert rotation orchestration.
- No PKI issuance/revocation automation.
- No remote-signing/unwrap KMS execution model yet (providers currently return key/TLS material to runtime).
