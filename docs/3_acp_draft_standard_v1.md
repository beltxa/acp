
# Agent Communication Protocol (ACP) – Draft Standard v1.0

## Overview

The Agent Communication Protocol (ACP) is a secure, transport‑agnostic communication protocol designed for collaboration between autonomous software agents across organizational and network boundaries.

ACP provides:

- Secure agent‑to‑agent messaging
- Multi‑recipient communication
- End‑to‑end encrypted payloads
- Transport independence
- Partial delivery tolerance
- Extensible enterprise profiles

ACP separates protocol, network infrastructure, and enterprise governance layers to enable both open adoption and commercial deployment.

---

# 1. Core Design Principles

## End‑to‑End Security
ACP encrypts payloads at the protocol layer so that intermediaries cannot read message content.

## Transport Independence
ACP messages may travel over:

- HTTP
- WebSocket
- Relay networks
- Peer‑to‑peer transports
- Message queues

## Multi‑Recipient Messaging
A single operation may target multiple agents atomically at intent level.

## Partial Delivery Tolerance
ACP assumes distributed environments where some recipients may fail or disappear.

## Infrastructure Optionality
Agents can communicate directly or via relays.

---

# 2. ACP Identity Model

ACP identities bind agent identifiers to cryptographic keys.

Identity structure:

- agent identifier
- public keys
- signed identity document
- optional trust profile

Example identifier:

agent:inventory.bot@companyA.com

Trust levels:

- self_asserted
- domain_verified
- enterprise_managed
- regulated_assured

Identity documents include:

- signing keys
- encryption keys
- endpoint hints
- relay hints
- validity metadata

---

# 3. Discovery Model

ACP discovery resolves agent identifiers into identity documents and reachability information.

Discovery layers:

1. Local cache
2. Domain-based discovery (.well-known/acp)
3. Relay-assisted discovery
4. Enterprise directories

Example discovery endpoint:

https://companyA.com/.well-known/acp/agents/inventory.bot

Discovery returns:

- identity document
- public keys
- transport options
- relay hints
- trust profile

---

# 4. Message Model

ACP messages consist of:

Routing Envelope (cleartext)
Protected Payload (encrypted)

Routing envelope contains metadata for delivery.

Protected payload contains encrypted application data.

---

# 5. Message Semantics

ACP defines a minimal set of protocol message classes.

Core classes:

SEND – application message  
ACK – protocol acceptance acknowledgement  
FAIL – structured rejection or error  
COMPENSATE – compensating instruction linked to prior operation  
CAPABILITIES – capability advertisement or negotiation

Required message fields:

- message_class
- message_id
- operation_id
- sender
- recipients
- context_id
- timestamp
- expires_at

Optional fields:

- correlation_id
- in_reply_to

Recipient protocol states:

PENDING  
DELIVERED  
ACKNOWLEDGED  
FAILED  
DECLINED  
EXPIRED

---

# 6. Encryption Model

ACP uses hybrid encryption.

Payload encryption:
AES‑256‑GCM (recommended)

Per‑recipient key wrapping:
Content encryption key wrapped using recipient public keys.

Authentication:
Messages signed with Ed25519 keys.

This enables secure multi‑recipient messaging without exposing payloads to relays.

---

# 7. Relay Network

ACP relays are intermediary nodes that forward encrypted ACP messages.

Relay responsibilities:

- receive ACP messages
- validate routing envelope
- forward messages
- optionally buffer encrypted messages

Relays must not decrypt payloads.

Relay routing modes:

Direct Delivery  
Relay Forwarding  
Store‑and‑Forward

Relays may be operated by:

- developers
- organizations
- infrastructure providers

---

# 8. Capability Negotiation

ACP capability negotiation determines compatibility between agents.

Capabilities may include:

- protocol versions
- crypto suites
- supported transports
- max payload size
- feature support (ACK, FAIL, COMPENSATE)
- protocol profiles

Example capability object:

{
  "agent_id": "agent:shipping.bot@companyB.com",
  "protocol_versions": ["1.0"],
  "crypto_suites": ["ACP-AES256-GCM+ED25519"],
  "transports": ["https", "websocket", "relay"],
  "limits": {"max_payload_bytes": 1048576}
}

Senders select the highest mutually compatible options.

---

# 9. SDK Model

ACP adoption depends heavily on SDK simplicity.

Example SDK usage:

from acp import Agent

agent = Agent.create("agent:inventory.bot@companyA.com")

agent.send(
    recipients=["agent:shipping.bot@companyB.com"],
    payload={"task": "ship_order"},
    context="order-123"
)

SDK responsibilities:

- key generation
- encryption
- signing
- discovery
- routing
- retry handling
- delivery tracking

---

# 10. Enterprise Premium Profile

Enterprise extensions may include:

- governance workspaces
- regulated identity frameworks
- deterministic delivery guarantees
- compliance audit logs
- enterprise relay networks
- policy‑driven coordination

These capabilities are intentionally outside the core ACP specification to preserve simplicity and open adoption.

---

# 11. Ecosystem Architecture

ACP ecosystem consists of three layers:

Protocol Layer – ACP open standard  
Network Layer – relay infrastructure and discovery services  
Enterprise Layer – governance, compliance, and regulated deployment

---

# 12. Vision

ACP aims to become the secure communication layer for AI agents, similar to how HTTP became the communication protocol for the web.

By separating protocol, infrastructure, and enterprise capabilities, ACP enables both widespread adoption and sustainable commercial ecosystems.
