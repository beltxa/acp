# ACP Key Provider Abstraction

Version: Draft v1

## Purpose

Define a pluggable interface for retrieving key material used by ACP identities and transport security.

The key provider abstraction allows ACP to work with:

- local file storage
- secret managers
- cloud KMS systems

without changing ACP protocol logic.

---

## Design Principle

ACP runtime must never depend directly on a specific secret storage system.

Instead:
ACP Runtime
│
Key Provider Interface
│
Provider Implementation

---

## Provider Types

### Local Provider
Reads keys from local files.

Used for:

- development
- demos

---

### Vault Provider

Retrieves keys from a Vault path.

Example:
 secret/acp/identities/john.chess

Vault returns:
 signing_key
 encryption_key
 tls_cert
 tls_key
---

### KMS Provider

Uses cloud KMS APIs.

Examples:

- AWS KMS
- Azure Key Vault
- GCP Cloud KMS

In this model KMS may:

- store keys
- wrap keys
- sign operations

---

## Provider Interface

Conceptual interface:

```python
class KeyProvider:

    def load_identity_keys(agent_id):
        pass

    def load_tls_material(agent_id):
        pass

    def load_ca_bundle():
        pass
```

---
## Runtime Behavior

ACP runtime should:
	1.	initialize provider
	2.	request keys when needed
	3.	cache briefly
	4.	avoid long-term storage

Configuration

Example config:
 key_provider: local

or 

 key_provider: vault
 vault_path: secret/acp

or 

  key_provider: kms
  provider: aws
  key_id: alias/acp-agent

### Security Rule

Key providers must ensure:
	•	private keys are never exposed unnecessarily
	•	access is logged where possible
	•	permissions follow least privilege

### Summary

The key provider abstraction ensures ACP can operate securely in enterprise environments without coupling protocol logic to a specific secret management system.

Implementation status:

- Python SDK: Local + Vault providers
- Java SDK: Local + Vault providers
