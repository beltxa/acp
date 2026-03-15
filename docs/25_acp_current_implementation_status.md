
# ACP Current Implementation Status

Version: Draft Snapshot

## Purpose
This document records the current implementation state of the Agent Communication Protocol (ACP) after completion of:

- Python SDK
- Java SDK
- Direct transport
- Relay transport
- AMQP transport binding
- MQTT transport binding
- Cross‑language interoperability tests

It provides a stable checkpoint before additional protocol work proceeds.

---

## Implemented Components

### SDKs
- Python ACP SDK
- Java ACP SDK

Capabilities implemented:

- Identity generation and loading
- Identity documents
- Discovery hints
- Message envelope construction
- Hybrid encryption (Ed25519 + X25519 + AES‑GCM)
- SEND, ACK, FAIL semantics
- Duplicate message tolerance
- Capability advertisement

---

### Transports

Supported transports:

| Transport | Status |
|----------|-------|
| Direct HTTP | Implemented |
| Relay HTTP | Implemented |
| AMQP | Implemented |
| MQTT | Implemented |

Not implemented yet:

- Kafka
- JMS
- P2P

HTTP hardening status:

- HTTPS-first policy is implemented for HTTP-based transport paths
- `http://` usage is rejected by default unless explicit insecure override is enabled
- local/dev/demo workflows remain supported via explicit override flags/settings

---

### Relay

Relay behavior:

- Stateless by default
- At‑least‑once delivery
- Duplicate tolerant
- AMQP fallback supported
- Payload encryption preserved

---

### Protocol Invariants Implemented

- Canonical ACP JSON message body
- Protocol‑layer encryption
- At‑least‑once delivery model
- Duplicate tolerance via `message_id`
- Terminal ACK/FAIL semantics

---

### Interoperability

Tested combinations:

- Python → Python
- Python → Java
- Java → Python

Across transports:

- Direct HTTP
- Relay HTTP
- AMQP
- MQTT

---

### Frozen Artifacts

The following have been frozen to prevent protocol drift:

- AMQP interoperability fixtures
- MQTT interoperability fixtures
- Transport binding abstractions
- Topic/address normalization rules
- ACK/FAIL terminal semantics

---

## Known Limitations

Current implementation intentionally excludes:

- Enterprise governance profile
- Event channel model
- Stateful relay mode
- Exactly‑once delivery
- Billing or infrastructure economics
- Policy engine or compliance features

---
### Relay Registration API (v1 limitation)

The current relay exposes only a minimal registration interface.

Current behavior:

- Registration writes are performed through a shared publish endpoint.
- Registration reads are resolved through discovery rather than a dedicated registry API.

This means that:

- `register put` and `register update` share the same underlying operation.
- `register show` uses relay discovery instead of querying a registry directly.

This model is sufficient for:

- demos
- early developer adoption
- lightweight operational workflows

A future ACP relay profile may introduce a formal registry management API with separate operations for:

- create / update registration
- retrieve registration
- list registered agents
- delete registration

---


## Next Potential Directions

Possible next development phases:

1. Rust relay rewrite
2. Transport conformance harness
3. Additional transport bindings (Kafka, P2P)
4. External developer release
