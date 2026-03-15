```md

# ACP Vault / KMS Integration Implementation Brief

## Goal

Add enterprise key management integration support to ACP using the new Key Provider abstraction.

ACP must support retrieving identity and TLS keys from:

- local files (existing)
- Vault
- cloud KMS systems

without changing ACP protocol semantics.

---

## Implementation Approach

Introduce a pluggable key provider interface.

acp.security.key_provider

Providers:

- LocalKeyProvider
- VaultKeyProvider
- KMSKeyProvider (future)

---

## Phase 1 Scope

Implement:

1. KeyProvider interface
2. Local provider wrapper (current behavior)
3. Vault provider
4. runtime configuration

Do not implement full KMS integrations yet.

---

## Vault Provider

Vault provider should:

- connect to Vault HTTP API
- authenticate via token or environment
- read secrets from configured path

Example path:
 secret/acp/identities/

Vault secret structure:
 signing_key
 encryption_key
 tls_cert
 tls_key
 ca_bundle

---

## Configuration Example
key_provider: vault
vault_url: https://vault.example.com
vault_path: secret/acp/identities
vault_token_env: VAULT_TOKEN

---

## Runtime Behavior

ACP runtime:

1. reads config
2. initializes provider
3. fetches keys on startup
4. caches keys in memory
5. refreshes when required

---

## CLI Integration

Add CLI support to show provider type.

Example:
 acp identity show

Output:
 Key provider: vault
 Vault path: secret/acp/identities/john.chess

---

## Security Rules

Provider implementations must:

- never log private keys
- respect TLS verification
- support explicit CA bundle configuration

---

## Out of Scope

Do not implement:

- dynamic secret rotation
- PKI enrollment
- certificate issuance
- cloud-specific IAM integrations
- automatic revocation workflows

These belong to later enterprise hardening phases.

---

## Deliverables

Codex should produce:

- key provider interface
- vault provider implementation
- config wiring
- minimal tests
- documentation updates