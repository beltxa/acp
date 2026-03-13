# ACP Codex Engineering Brief

## Purpose

This document consolidates the minimum ACP materials needed for Codex to begin implementation work.

Codex should treat this file as the primary engineering source of truth for the first implementation phase.

The goal is **not** to build the full enterprise platform. The goal is to build a **minimal reference implementation of ACP v1** that proves the protocol and enables developer adoption.

---

## 1. Implementation Goal

Build a minimal but real ACP reference implementation with these components:

1. **ACP SDK**
   - create/load agent identity
   - generate identity document
   - perform discovery
   - encrypt/sign outbound messages
   - decrypt/verify inbound messages
   - send messages to one or more recipients
   - support `SEND`, `ACK`, `FAIL`, `CAPABILITIES`
   - optionally include `COMPENSATE` as a message class even if not fully orchestrated yet

2. **Reference Relay**
   - receive ACP messages
   - validate routing envelope
   - forward messages
   - optionally buffer encrypted messages in memory
   - never decrypt payloads

3. **Discovery / Identity Hosting**
   - support `.well-known` style identity document resolution
   - expose static identity document and relay hints

The first implementation should optimize for:
- simplicity
- clarity
- developer usability
- protocol correctness

It should **not** optimize for:
- enterprise governance
- full relay economics
- premium compliance features
- distributed transactions
- regulated-industry controls

---

## 2. Recommended First Implementation Scope

### In scope
- ACP core message structure
- routing envelope + protected payload
- hybrid encryption model
- one-to-one and one-to-many send
- per-recipient delivery outcomes
- identity document generation and validation
- discovery via cache + `.well-known`
- minimal relay forwarding
- simple SDK API
- structured `ACK` / `FAIL`

### Out of scope for v1 prototype
- MLS / ratcheting
- blockchain
- premium governance workspaces
- deterministic enterprise delivery SLAs
- heavy capability bargaining
- full store-and-forward persistence
- production-grade authentication and billing
- multi-region relay federation
- advanced policy engine

---

## 3. Target Developer Experience

The SDK must make ACP feel simple.

### Example usage

```python
from acp import Agent

agent = Agent.load_or_create("agent:inventory.bot@example.com")

agent.send(
    recipients=[
        "agent:shipping.bot@example.com",
        "agent:finance.bot@example.com"
    ],
    payload={
        "type": "task_request",
        "data": {
            "task": "ship_order",
            "order_id": "12345"
        }
    },
    context="order-12345"
)
```

The SDK should hide:
- key generation
- key storage
- identity document creation
- discovery resolution
- encryption
- signing
- transport selection
- retries
- basic delivery tracking

---

## 4. ACP Core Model

### 4.1 Identity

Each agent has:
- `agent_id`
- signing key
- encryption key
- signed identity document
- optional trust profile

Recommended defaults:
- signing: `Ed25519`
- encryption: `X25519`
- payload encryption: `AES-256-GCM`

### 4.2 Discovery

Discovery order:
1. local cache
2. `.well-known` domain lookup
3. relay hints
4. enterprise directory later

Recommended `.well-known` pattern:

```text
https://<domain>/.well-known/acp/agents/<agent_name>
```

### 4.3 Message structure

ACP messages consist of:

1. **Routing Envelope** (cleartext)
2. **Protected Payload** (encrypted)

### 4.4 Required routing envelope fields

- `acp_version`
- `message_class`
- `message_id`
- `operation_id`
- `timestamp`
- `expires_at`
- `sender`
- `recipients`
- `context_id`
- `crypto_suite`

Optional:
- `correlation_id`
- `in_reply_to`

### 4.5 Protected payload

Should include:
- encrypted payload ciphertext
- IV / nonce
- authentication tag
- per-recipient wrapped content keys
- sender signature
- payload hash

---

## 5. Message Classes

Implement these first:

### `SEND`
Primary application message.

### `ACK`
Protocol-level acceptance:
- signature verified
- payload decrypted
- accepted into processing

### `FAIL`
Structured rejection with machine-readable reason code.

Suggested reason codes:
- `UNSUPPORTED_VERSION`
- `UNSUPPORTED_CRYPTO_SUITE`
- `UNSUPPORTED_MESSAGE_CLASS`
- `INVALID_SIGNATURE`
- `EXPIRED_MESSAGE`
- `POLICY_REJECTED`
- `PAYLOAD_TOO_LARGE`

### `CAPABILITIES`
Optional but useful for prototype completeness.
May initially be implemented as static response data.

### `COMPENSATE`
Define the message class and serialization now.
Full orchestration behavior can come later.

---

## 6. Delivery Semantics

ACP supports one logical multi-recipient operation.

A single `send()` may target multiple recipients.

That is **atomic at intent level**, not atomic at delivery level.

Each recipient may independently move through states:
- `PENDING`
- `DELIVERED`
- `ACKNOWLEDGED`
- `FAILED`
- `DECLINED`
- `EXPIRED`

The prototype only needs lightweight tracking of these states.

---

## 7. Capability Negotiation

Use **capability advertisement**, not heavy negotiation.

Static capabilities may include:
- protocol versions
- crypto suites
- transports
- max payload size
- support flags for `ACK`, `FAIL`, `COMPENSATE`

The sender chooses the highest mutually compatible combination.

A runtime `CAPABILITIES` exchange may be implemented simply.

---

## 8. Relay Behavior

The reference relay should:

- accept ACP messages over HTTP
- validate envelope structure
- check expiry
- inspect recipients
- route or forward
- optionally buffer encrypted payloads in memory

The relay must:
- never decrypt payloads
- never modify payloads
- operate as untrusted infrastructure for message confidentiality

For the first version, a **single relay service** is enough.

---

## 9. Suggested Implementation Shape

### SDK
Recommended language:
- Python first

Reason:
- fastest prototyping
- strongest AI/developer ecosystem fit

Optional later:
- TypeScript / Node SDK

### Relay
Recommended language:
- Python first for speed, or Go for cleaner service implementation

For the first pass, consistency matters more than raw performance.

---

## 10. Minimal Repository Layout

```text
/acp-sdk-python
    /acp
        identity.py
        discovery.py
        crypto.py
        messages.py
        transport.py
        agent.py
        capabilities.py
        relay_client.py

/acp-relay
    app.py
    routes.py
    routing.py
    validation.py
    storage.py

/examples
    send_basic.py
    send_multi_recipient.py
    capabilities_demo.py

/docs
    protocol-summary.md
```

---

## 11. Minimal Milestones

### Milestone 1
Identity + message serialization + crypto primitives

### Milestone 2
SDK `send()` for one recipient over direct HTTP

### Milestone 3
SDK `send()` for multiple recipients using wrapped keys

### Milestone 4
Reference relay with forwarding

### Milestone 5
Discovery via `.well-known`

### Milestone 6
`ACK` / `FAIL` / delivery state handling

### Milestone 7
Examples and documentation

---

## 12. ACP Interaction Patterns to Support Early

The prototype should be able to demonstrate:

1. task delegation
2. request/response
3. multi-agent task distribution
4. event broadcast
5. failure + compensation message emission

These patterns are enough to show ACP’s value.

---

## 13. Non-Goals for the First Prototype

Do not build:
- enterprise premium profile
- billing system
- governance workspaces
- regulated controls
- full persistence model
- distributed workflow engine

Those belong after the protocol is proven.

---

## 14. Engineering Rule

When there is any ambiguity, prefer:
- simpler implementation
- cleaner protocol boundary
- better developer experience
- protocol clarity over completeness

The first ACP implementation should feel like a **reference protocol kit**, not a full enterprise platform.
