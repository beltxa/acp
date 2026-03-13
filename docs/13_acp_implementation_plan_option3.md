
# ACP Implementation Plan (Option 3)
## Python SDK + Python Relay First, Then Relay Rewrite in Rust

## 1. Objective

Build the first working ACP prototype using:

- **Python SDK**
- **Python relay**
- **Java minimal ACP client library** for reuse of existing poker agents
- later **Rust relay rewrite** once protocol behavior is validated

This approach optimizes for:

- speed of execution
- Codex productivity
- protocol learning
- fast demos
- low implementation risk

It does not optimize initially for:

- maximum relay performance
- production hardening
- full enterprise-grade infrastructure

---

## 2. Why Option 3

### Stage 1
Build the whole first prototype in Python where possible:
- fastest iteration
- easiest debugging
- strongest fit for early AI/agent developer adoption

### Stage 2
Once protocol behavior is stable:
- rewrite the relay in Rust
- preserve the wire protocol and relay API
- keep SDK behavior unchanged

This gives ACP a fast path to a working system while preserving a credible long-term infrastructure direction.

---

## 3. Scope of the First Build

### In scope
- ACP message model
- identity document generation
- `.well-known` discovery
- hybrid encryption
- one-to-one messaging
- one-to-many messaging
- per-recipient key wrapping
- relay forwarding
- protocol-level `ACK`
- protocol-level `FAIL`
- basic capability advertisement
- duplicate-safe handling
- simple examples and demo applications

### Out of scope
- premium enterprise profile
- event channels
- deterministic delivery guarantees
- stateful relay profile
- billing
- relay federation across many operators
- advanced governance
- MLS or ratcheting
- blockchain

---

## 4. Target Deliverables

### Deliverable A — Python ACP SDK
Provides:
- identity management
- identity document creation
- discovery resolution
- message building
- encryption and signing
- transport logic
- deduplication helpers
- clean developer API

### Deliverable B — Python Relay
Provides:
- HTTP ingress
- envelope validation
- best-effort forwarding
- optional short-lived in-memory buffering
- duplicate-tolerant stateless routing

### Deliverable C — Minimal Java ACP Client Library
Provides:
- enough ACP support to let existing Java poker agents communicate over ACP

### Deliverable D — Examples / Demo
Includes:
- Python-to-Python example
- Java-to-Python poker demo path
- multi-recipient send example
- partial failure + `COMPENSATE` example

### Deliverable E — Rust Relay Rewrite Plan
A follow-on implementation once the relay behavior is validated.

---

## 5. Proposed Repository Structure

```text
/acp-sdk-python
    /acp
        agent.py
        identity.py
        identity_doc.py
        discovery.py
        crypto.py
        envelopes.py
        message_classes.py
        transport.py
        relay_client.py
        capabilities.py
        dedup.py

/acp-relay-python
    app.py
    routes.py
    validation.py
    forwarding.py
    routing.py
    memory_buffer.py
    models.py

/acp-sdk-java
    src/main/java/...
    Identity.java
    IdentityDocument.java
    MessageEnvelope.java
    ProtectedPayload.java
    CryptoSupport.java
    DiscoveryClient.java
    TransportClient.java
    AcpAgent.java

/examples
    python_send_basic.py
    python_send_multi.py
    python_capabilities_demo.py
    poker_demo_java_python.md

/docs
    protocol-summary.md
    local-dev-setup.md
```

---

## 6. Phase Plan

## Phase 1 — Protocol Core in Python

### Goal
Build the ACP protocol primitives and validate local serialization.

### Tasks
1. Create project structure
2. Define ACP routing envelope classes
3. Define protected payload classes
4. Implement message serialization/deserialization
5. Implement identity document format
6. Implement key generation
7. Implement signing and verification
8. Implement payload encryption and recipient key wrapping

### Exit criteria
- ACP messages can be created, signed, encrypted, serialized, deserialized, verified, and decrypted locally

---

## Phase 2 — Python SDK Minimal Send/Receive

### Goal
Build a minimal SDK with direct HTTPS delivery.

### Tasks
1. Implement `Agent.load_or_create()`
2. Implement local identity document generation
3. Implement direct endpoint sending
4. Implement inbound HTTP handler pattern
5. Implement `ACK` and `FAIL`
6. Implement local deduplication by `message_id`

### Exit criteria
- one Python agent can send directly to another Python agent over ACP

---

## Phase 3 — Discovery

### Goal
Enable identity resolution through `.well-known`.

### Tasks
1. Implement local discovery cache
2. Implement `.well-known` fetch
3. Validate remote identity documents
4. Add relay hints and direct endpoint resolution
5. Add capability document support

### Exit criteria
- one agent can resolve another from domain-based discovery and send successfully

---

## Phase 4 — Python Relay

### Goal
Implement the first stateless ACP relay.

### Tasks
1. HTTP ingress endpoint for ACP messages
2. Envelope validation
3. Expiry validation
4. Route selection
5. Forward to direct endpoint or next relay
6. Optional short-lived in-memory buffering
7. Allow duplicate forwarding behavior
8. Logging and basic observability

### Exit criteria
- agents can communicate through a Python relay

---

## Phase 5 — Multi-Recipient Operations

### Goal
Support one logical send to multiple recipients.

### Tasks
1. Add `operation_id`
2. Encrypt payload once
3. Wrap content key per recipient
4. Track per-recipient outcomes
5. Handle partial `ACK` / `FAIL`
6. Emit `COMPENSATE` message shape

### Exit criteria
- one agent can send one ACP operation to multiple recipients and observe partial outcomes

---

## Phase 6 — Minimal Java ACP Client Library

### Goal
Enable reuse of existing Java poker agents.

### Tasks
1. Define Java ACP model classes
2. Implement Java key loading/generation
3. Implement Java envelope building
4. Implement Java encryption/signing
5. Implement Java HTTP transport
6. Implement Java `ACK` / `FAIL` handling
7. Build Java poker integration example

### Exit criteria
- Java poker dealer or player can send ACP messages to Python agents via relay or direct endpoint

---

## Phase 7 — Demonstration & Stabilization

### Goal
Produce a convincing end-to-end demo.

### Demonstrations
1. Python agent to Python agent
2. Python agent to multiple recipients
3. Partial failure and compensation
4. Java poker dealer to player agents over ACP

### Exit criteria
- ACP can be demonstrated as a protocol rather than just a local SDK

---

## Phase 8 — Rust Relay Rewrite

### Goal
Replace the Python relay with a Rust implementation without changing ACP protocol semantics.

### Tasks
1. Freeze relay HTTP/wire behavior
2. Define relay conformance tests
3. Reimplement stateless relay in Rust
4. Ensure compatibility with Python SDK and Java client
5. Preserve duplicate-tolerant behavior

### Exit criteria
- Rust relay is drop-in compatible with the Python prototype

---

## 7. Delivery Semantics

ACP v1 relay behavior should assume:

- **stateless by default**
- **at-least-once delivery**
- **duplicate messages may occur**
- **recipients must deduplicate using `message_id`**

This must be reflected in both SDK and Java client implementations.

---

## 8. Recommended Crypto Defaults

Use these defaults consistently in the first prototype:

- `Ed25519` for signatures
- `X25519` for recipient encryption / key agreement
- `AES-256-GCM` for payload encryption
- JSON serialization for protocol objects
- base64 encoding for binary fields where needed

---

## 9. Developer API Goal

Python SDK target:

```python
from acp import Agent

agent = Agent.load_or_create("agent:inventory.bot@example.com")

agent.send(
    recipients=["agent:shipping.bot@example.com"],
    payload={
        "type": "task_request",
        "data": {"task": "ship_order"}
    },
    context="order-123"
)
```

Java client target:

```java
AcpAgent agent = AcpAgent.loadOrCreate("agent:dealer@poker.demo");

agent.send(
    List.of("agent:player1@poker.demo"),
    payload,
    "hand-123"
);
```

---

## 10. Risks and Mitigations

### Risk: crypto interoperability between Python and Java
Mitigation:
- use standard algorithms
- define canonical JSON handling early
- create shared test vectors

### Risk: overbuilding the relay
Mitigation:
- keep relay stateless and minimal
- do not add enterprise features yet

### Risk: SDK complexity grows too early
Mitigation:
- implement only the message classes and flows required for the first demos

### Risk: Java library scope expands too much
Mitigation:
- keep Java implementation focused on poker demo needs only

---

## 11. Recommended Immediate Next Actions

1. Start Python SDK core
2. Build Python relay
3. Freeze message format and crypto encoding
4. Create Java ACP client spec
5. Implement Java minimal client
6. Run poker demo over ACP
7. Prepare Rust relay rewrite only after behavior is stable

---

## 12. Summary

Option 3 is the most pragmatic ACP path:

- Python to learn fast
- Java to prove cross-language protocol value
- Rust later to harden the relay

This creates the fastest route to a credible demonstration and a durable technical foundation.
