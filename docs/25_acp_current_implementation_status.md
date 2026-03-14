
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

## Next Potential Directions

Possible next development phases:

1. Rust relay rewrite
2. Transport conformance harness
3. Additional transport bindings (Kafka, P2P)
4. External developer release
