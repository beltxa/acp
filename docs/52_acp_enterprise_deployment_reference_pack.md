
# ACP Enterprise Deployment Reference Pack

Version: Draft v1

## Purpose
Provide a practical reference configuration for deploying ACP securely in enterprise environments.

This pack accompanies the ACP Enterprise Security Deployment Profile and helps operators deploy ACP components consistently.

## Reference Architecture

Agents
   │
ACP SDK Runtime
   │
HTTPS / mTLS
   │
Relay (optional)
   │
Enterprise Secret Store (Vault / KMS)
   │
Enterprise PKI

## Reference Deployment Components

### Agent Runtime
Runs ACP SDK with configured key provider and transport settings.

Responsibilities:
- identity loading
- message encryption/signing
- transport negotiation
- discovery interaction

### Relay
Optional routing node for:

- discovery assistance
- message routing
- network decoupling

Relay does not decrypt ACP payloads.

### Key Provider
Handles retrieval of sensitive materials.

Example providers:
- LocalKeyProvider
- VaultKeyProvider

### Transport Security
Transport layer should use:

- HTTPS for all endpoints
- optional mTLS for enterprise deployments

### Discovery Layer
Responsible for mapping agent identities to reachable endpoints.

## Example Deployment Layout

/acp/
   config/
      agent.yaml
      relay.yaml
   certs/
      ca_bundle.pem
      client.pem
      client.key
   identities/
      john.identity.json
      ricardo.identity.json

## Example Agent Config

agent_id: agent:john.chess@demo

key_provider: vault
vault_url: https://vault.company.net
vault_path: secret/acp/identities

transport:
  http:
    endpoint: https://agent.company.net/acp
    mtls_enabled: true

## Enterprise Profile Config Field Set (Python + Java)

Use this common schema wherever practical:

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

Reference examples are available in:

- `examples/enterprise/local-provider-https.yaml`
- `examples/enterprise/vault-provider-https.yaml`
- `examples/enterprise/vault-provider-https-mtls.yaml`

## Operational Best Practices

1. Store all private keys in secret manager.
2. Use enterprise CA-signed certificates for transport endpoints.
3. Rotate keys periodically.
4. Monitor relay routing statistics.
5. Keep insecure HTTP disabled in production.

## Reference CLI Usage

Check identity:

acp identity show --agent-id agent:john.chess@demo

Check relay:

acp relay status

Check transport:

acp transport probe --agent-id agent:ricardo.chess@demo

## Summary

The ACP enterprise deployment model:

- separates protocol identity from infrastructure trust
- integrates with enterprise PKI and secret stores
- supports secure agent communication across environments
