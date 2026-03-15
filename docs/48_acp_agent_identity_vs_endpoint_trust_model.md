# ACP Agent Identity vs Endpoint Trust Model

Version: Draft v1

## Purpose

This document clarifies how ACP separates **agent identity** from **endpoint trust**.

The goal is to make ACP easy to adopt in enterprise environments by allowing existing
infrastructure trust models (TLS, PKI, service mesh, broker authentication, etc.)
to coexist with ACP’s protocol-level identity and encryption.

This separation lowers adoption friction while preserving strong end‑to‑end security.

---

# 1. Two-Layer Identity Model

ACP uses two distinct identity layers:

| Layer | Responsibility |
|------|---------------|
| Agent Identity | Persistent logical identity of an autonomous agent |
| Endpoint Identity | Authentication of the network endpoint hosting the agent |

These layers are intentionally independent.

---

# 2. Agent Identity (ACP Layer)

Agent identity is defined by ACP itself.

Example:

agent:john.chess@demo

Agent identity includes:

- identity document
- signing key
- encryption key
- discovery metadata

Agent identity provides:

- cryptographic message authenticity
- persistent identity across infrastructure changes
- stable logical agent identity

ACP messages are **signed by the agent identity key**.

---

# 3. Endpoint Identity (Infrastructure Layer)

Endpoint identity is how the network path is authenticated.

Examples:

- HTTPS server certificate
- mTLS client certificate
- private enterprise CA
- service mesh identity
- AMQP/MQTT broker authentication

Endpoint identity answers the question:

“Can I trust the network endpoint hosting this agent?”

Endpoint identity is typically governed by enterprise infrastructure.

---

# 4. Relationship Between the Layers

The discovery system binds agent identity to reachable endpoints.

Example discovery result:

{
  "agent_id": "agent:ricardo.chess@demo",
  "service": {
    "http": {
      "endpoint": "https://agent.example.com/acp",
      "security_profile": "mtls"
    }
  }
}

The client verifies:

1. Endpoint trust using infrastructure mechanisms
2. Agent identity using ACP signatures

Both layers must succeed for communication to proceed.

---

# 5. Example Lifecycle

### Initial deployment

Agent runs locally:

agent:ricardo.chess@demo  
endpoint: http://localhost:9000/acp

Agent identity remains constant.

Endpoint trust is minimal (local dev).

---

### Relay deployment

Agent registers with relay:

endpoint: https://relay.example.com

Relay endpoint trust validated via TLS.

Agent identity verified via ACP signatures.

---

### Cloud migration

Agent moves to AWS:

endpoint: https://aws-agent.example.com/acp  
certificate: enterprise CA

Endpoint identity changes.

Agent identity remains the same.

Clients verify both.

---

# 6. Security Properties

This layered model provides:

- **Agent continuity** independent of infrastructure location
- **Infrastructure compatibility** with existing enterprise trust models
- **Defense in depth** via both protocol and transport authentication

If endpoint trust fails → connection rejected.

If agent signature fails → message rejected.

---

# 7. Enterprise Policy

Enterprises may enforce policies such as:

- only accept endpoints with enterprise CA certificates
- require mTLS profile
- restrict transports
- require specific relay infrastructure

These policies apply to endpoint trust, not ACP identity.

---

# 8. Benefits

This model:

- avoids replacing enterprise PKI
- reduces adoption friction
- supports incremental migration
- allows ACP to coexist with existing infrastructure security

---

# 9. Strategic Implication

ACP does not attempt to replace enterprise trust infrastructure.

Instead, ACP provides:

- agent identity
- secure messaging semantics
- discovery and routing

while leveraging existing infrastructure for endpoint trust.

This makes ACP significantly easier to adopt in enterprise environments.

---

# Summary

ACP separates:

**Who the agent is** (agent identity)

from

**Where the agent runs and how the network is trusted** (endpoint identity)

This separation allows ACP to integrate cleanly with existing enterprise security systems
while maintaining strong protocol-level guarantees.
