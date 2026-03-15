# ACP Security and Trust Architecture Overview

Version: Draft v1

## Purpose

This document provides a single integrated architecture view of ACP security and trust.

It combines:

- agent identity
- endpoint trust
- discovery
- transports
- relays
- enterprise key management

The goal is to explain how ACP fits into enterprise environments without replacing existing trust infrastructure.

---

# 1. Integrated View

```text
                  ┌──────────────────────────────┐
                  │      Enterprise Key / Cert   │
                  │      Management Layer        │
                  │  (Local / Vault / KMS / PKI) │
                  └──────────────┬───────────────┘
                                 │
                                 │ supplies keys / certs
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ACP Agent Runtime                           │
│                                                                     │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │ ACP Agent Identity   │     │ Endpoint Trust / Transport Sec. │  │
│  │                      │     │                                  │  │
│  │ - identity document  │     │ - HTTPS                         │  │
│  │ - signing key        │     │ - optional mTLS                 │  │
│  │ - encryption key     │     │ - broker auth (AMQP / MQTT)     │  │
│  │ - message signatures │     │ - enterprise CA / trust-store   │  │
│  └──────────┬───────────┘     └──────────────┬───────────────────┘  │
│             │                                 │                      │
│             └──────────────┬──────────────────┘                      │
│                            │                                         │
│                            ▼                                         │
│                  ACP Message Processing                              │
│          - encrypt / decrypt payloads                                │
│          - verify signatures                                         │
│          - deduplicate messages                                      │
│          - select delivery path                                      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Discovery / Registry │
                  │                      │
                  │ - resolve agent id   │
                  │ - return endpoints   │
                  │ - return hints       │
                  │ - bind identity to   │
                  │   current reachability│
                  └──────────┬───────────┘
                             │
                             ▼
              ┌─────────────────────────────────────┐
              │       Transport / Routing Layer     │
              │                                     │
              │  Direct HTTP(S)                     │
              │  Relay HTTP(S)                      │
              │  AMQP                               │
              │  MQTT                               │
              │  future: Kafka / P2P / JMS         │
              └─────────────────────────────────────┘
```

---

# 2. Layer Responsibilities

## A. Enterprise Key / Certificate Management Layer

This layer controls key custody and certificate material.

Typical implementations:

- local files
- HashiCorp Vault
- AWS KMS / Secrets Manager
- Azure Key Vault
- GCP KMS
- enterprise PKI

Responsibilities:

- store agent signing keys
- store agent encryption keys
- store TLS server/client certificates
- provide CA bundles / trust material
- support audit and rotation processes

This layer does not change ACP protocol behavior.

---

## B. ACP Agent Identity Layer

This is the ACP-native identity layer.

Responsibilities:

- persistent logical agent identity
- message signing
- payload encryption identity
- identity continuity across infrastructure changes

Example:

```text
agent:ricardo.chess@demo
```

This is what the protocol recognizes as the agent.

---

## C. Endpoint Trust Layer

This is the infrastructure trust layer.

Responsibilities:

- authenticate transport endpoints
- validate TLS certificates
- support optional mTLS
- support broker authentication on non-HTTP transports

Examples:

- HTTPS server certificate
- mTLS client certificate
- private enterprise CA
- service mesh identity
- broker credentials

This layer answers:

> Can I trust the endpoint I am connected to?

---

## D. Discovery / Registry Layer

This layer binds ACP identity to current reachability.

Responsibilities:

- resolve agent identity
- return endpoint hints
- return relay hints
- return transport security profile hints
- support mobility without changing logical agent identity

Example output:

```json
{
  "agent_id": "agent:ricardo.chess@demo",
  "service": {
    "http": {
      "endpoint": "https://agent.example.com/acp",
      "security_profile": "mtls"
    }
  }
}
```

---

## E. Transport / Routing Layer

This layer carries ACP messages.

Supported / planned transports:

- direct HTTP(S)
- relay HTTP(S)
- AMQP
- MQTT
- future Kafka / P2P / JMS

Responsibilities:

- move ACP messages
- preserve canonical ACP payload
- preserve delivery semantics
- remain transport-specific, not protocol-defining

---

# 3. Security Verification Flow

When one ACP agent talks to another:

## Step 1 — Discovery
Resolve the target agent identity and obtain endpoint / transport hints.

## Step 2 — Endpoint trust validation
Validate the endpoint using infrastructure controls:
- HTTPS
- optional mTLS
- broker auth
- enterprise CA

## Step 3 — ACP identity verification
Verify ACP identity document and message signatures.

## Step 4 — Message security
Encrypt, decrypt, and verify ACP payloads and signatures.

This gives ACP layered, defense-in-depth security.

---

# 4. Key Architectural Principle

ACP separates:

- **Who the agent is** → ACP identity
- **How the endpoint is trusted** → endpoint trust
- **Where the keys live** → key provider / enterprise custody
- **How messages move** → transport binding

This separation lowers adoption friction because enterprises can reuse:

- existing PKI
- existing trust stores
- existing broker security
- existing secret managers

without giving up ACP’s protocol-level guarantees.

---

# 5. Enterprise Positioning

This architecture lets ACP be positioned as:

- protocol-secure by design
- transport-secure by default
- enterprise-hardenable through optional profiles
- compatible with existing enterprise trust infrastructure

This is the strongest enterprise story for ACP because it complements, rather than replaces, infrastructure security.

---

# 6. Summary

ACP security and trust architecture consists of:

1. enterprise key and certificate custody
2. ACP logical agent identity
3. endpoint trust via TLS / mTLS / broker auth
4. discovery binding identity to reachability
5. transport bindings carrying canonical ACP messages

Together, these layers provide a practical and adoptable security model for autonomous agents.

Reference deployment profile:

- `50_acp_enterprise_security_deployment_profile.md` (HTTPS-first + optional mTLS + Vault-backed key custody)
