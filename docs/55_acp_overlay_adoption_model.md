
# ACP Overlay Adoption Model

Version: Draft v1

## Purpose

This document defines the **ACP Overlay Adoption Model**, which describes how organizations can adopt ACP incrementally without replacing their existing infrastructure.

The model distinguishes between:

- **Overlay Mode** — ACP layered on top of existing systems
- **Native Mode** — ACP as the primary communication fabric

The objective is to **minimize adoption friction** while allowing systems to evolve toward a full ACP-native architecture over time.

---

# 1. The Adoption Problem

Organizations already run complex communication infrastructures:

- REST APIs
- webhooks
- service meshes
- message brokers (AMQP, MQTT, Kafka)
- VPN-connected systems
- internal event buses

Replacing these systems to adopt a new protocol is rarely acceptable.

Therefore, ACP must allow **incremental adoption**.

---

# 2. Overlay Mode

Overlay Mode allows ACP to be added **on top of existing communication patterns**.

Example existing system:

Service A → HTTPS → Service B

ACP Overlay:

Service A → HTTPS → Service B  
(with ACP envelope + identity + encryption)

In this mode:

- the existing transport remains unchanged
- ACP message semantics are added
- ACP identity is introduced
- payload signing and encryption are applied

No infrastructure replacement is required.

---

# 3. Overlay Mode Capabilities

Overlay deployments typically use:

- ACP message envelope
- ACP identity documents
- message signing
- payload encryption
- existing HTTP or broker transport

Optional enhancements:

- static discovery configuration
- limited CLI-based registration
- local identity storage

Overlay mode intentionally minimizes operational change.

---

# 4. Native Mode

Native Mode occurs when ACP becomes the primary communication fabric.

Example:

Agent  
   │  
ACP Runtime  
   │  
Relay / Direct Transport  
   │  
Other Agents

Native deployments use:

- ACP discovery services
- relay routing
- transport negotiation
- enterprise security profiles
- managed infrastructure

This mode provides the full ACP feature set.

---

# 5. Migration Path

ACP adoption can progress through stages.

### Stage 1 — Overlay Introduction

- ACP envelope added to existing HTTP or broker flows
- local identities
- minimal configuration

### Stage 2 — Overlay Expansion

- standardized ACP identity usage
- CLI tooling
- optional discovery services
- stronger transport security

### Stage 3 — Hybrid Mode

- some ACP-native agents
- some overlay agents
- relay routing introduced
- enterprise key custody integrated

### Stage 4 — Native Mode

- ACP discovery registry
- relay network
- enterprise security profile
- governed deployment environment

Each stage builds on the previous one without requiring architectural replacement.

---

# 6. Enterprise Security in Overlay Mode

Overlay mode still supports enterprise security controls.

Transport layer may use:

- HTTPS
- optional mTLS
- broker authentication

Key custody may use:

- local files (dev mode)
- Vault or KMS providers (enterprise mode)

ACP identity verification still occurs at the protocol layer.

This allows enterprises to reuse existing trust infrastructure.

---

# 7. Benefits of the Overlay Model

The overlay adoption strategy provides:

- low adoption friction
- compatibility with existing systems
- gradual migration to richer capabilities
- easier enterprise approval

Organizations can experiment with ACP without redesigning their architecture.

---

# 8. Strategic Implication

Protocols typically succeed when developers can adopt them without permission.

Overlay mode enables this by allowing ACP to be used immediately with:

- existing HTTP services
- existing message brokers
- existing infrastructure security

Over time, overlay deployments can evolve into ACP-native systems.

---

# 9. Summary

The ACP Overlay Adoption Model allows ACP to:

1. start as a lightweight protocol layer on existing infrastructure
2. standardize identity and message semantics
3. gradually introduce discovery, relay routing, and enterprise governance

This incremental path significantly reduces the barriers to adoption.
