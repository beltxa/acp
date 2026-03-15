# ACP Enterprise Key and Certificate Management

Version: Draft v1

## 1. Purpose

This document defines how ACP handles key and certificate material in enterprise deployments.

ACP currently supports:

- local key storage for identities
- HTTPS transport with certificate validation
- optional mTLS transport profile

Enterprise environments often require centralized key custody, auditing, and rotation.

This document defines the **enterprise key-management model** without changing ACP protocol semantics.

---

## 2. Security Layers

ACP security consists of three layers:

### Protocol Layer
- ACP identity documents
- signing keys
- message encryption keys

### Transport Layer
- HTTPS
- optional mTLS profile

### Key Custody Layer
- local filesystem provider
- external secret manager provider
- enterprise key management provider

The key custody layer determines **where keys are stored and retrieved**, not how the protocol operates.

---

## 3. Current Default (Developer Mode)

By default ACP stores key material locally.

Typical layout:
~/.acp/identities//
identity.json
signing_key.pem
encryption_key.pem

This mode is intended for:

- development
- demos
- lightweight deployments

---

## 4. Enterprise Requirements

Enterprise deployments usually require:

- centralized secret storage
- controlled access to keys
- audit logging
- rotation policies
- integration with PKI systems

Typical solutions include:

- HashiCorp Vault
- AWS KMS
- Azure Key Vault
- GCP KMS

ACP must allow these systems to supply keys.

---

## 5. Key Management Model

ACP separates **protocol keys** from **key custody**.

ACP Identity
│
Key Provider Interface
│
Key Store Implementation

This allows ACP to retrieve keys from different sources without changing protocol behavior.

---

## 6. Key Types

ACP uses several key types:

| Key Type | Purpose |
|--------|---------|
| identity signing key | authenticate agent |
| encryption key | encrypt payloads |
| TLS server cert | HTTPS endpoint identity |
| TLS client cert | mTLS authentication |

Key providers must support retrieval of these materials.

---

## 7. Key Lifecycle

Recommended lifecycle:

1. Key generation
2. Storage in provider
3. Controlled access by ACP runtime
4. Rotation
5. Revocation if compromised

ACP runtime should never assume key permanence.

---

## 8. Security Principle

ACP must follow these rules:

- protocol logic must not depend on key storage location
- private keys must never appear in logs
- secret managers should be accessed only at runtime
- keys should be cached minimally

---

## 9. Future Extensions

Possible future capabilities:

- automatic key rotation
- certificate renewal
- PKI integration
- policy-driven key usage

These belong to enterprise deployment layers, not ACP core protocol.

---

## 10. Summary

ACP supports enterprise security by:

- separating protocol from key custody
- allowing pluggable secret management
- supporting HTTPS and optional mTLS
- enabling integration with external key management systems

Current implementation note:

- Python SDK and Java SDK both expose `local` and `vault` key providers for identity keys and HTTP TLS material loading.
