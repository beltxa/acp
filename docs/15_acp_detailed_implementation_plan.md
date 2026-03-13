
# ACP Detailed Implementation Plan
## Execution Plan for the First ACP Prototype

## 1. Objective

Build the first working ACP prototype using:

- Python ACP SDK
- Python stateless relay
- minimal Java ACP client library for existing poker agents
- later Rust relay rewrite after protocol behavior is validated

This plan translates the high-level implementation strategy into a concrete execution sequence.

---

## 2. Delivery Principles

All implementation work should follow these rules:

1. Prefer protocol correctness over feature breadth
2. Keep the first implementation small and readable
3. Build only what is needed for the first end-to-end demo
4. Keep relays stateless by default
5. Assume at-least-once delivery and duplicate tolerance
6. Preserve cross-language interoperability from the beginning
7. Freeze message format and crypto encoding early
8. Avoid premium-profile and enterprise-only features until the protocol is proven

---

## 3. Scope of the First Prototype

### In scope
- identity generation and loading
- signed identity documents
- `.well-known`-style discovery
- routing envelope and protected payload
- Ed25519 signatures
- X25519 recipient key wrapping
- AES-256-GCM payload encryption
- direct HTTP delivery
- stateless relay forwarding
- one-to-one messaging
- one-to-many messaging
- `SEND`, `ACK`, `FAIL`
- `COMPENSATE` message structure
- basic `CAPABILITIES`
- recipient deduplication by `message_id`
- Python/Python interoperability
- Java/Python interoperability for poker demo

### Out of scope
- premium enterprise profile
- event channels
- stateful relay profile
- delivery SLAs
- billing
- governance workspaces
- policy engine
- blockchain
- MLS / ratcheting
- large-scale federation

---

## 4. Recommended Repositories

```text
/acp-sdk-python
/acp-relay-python
/acp-sdk-java
/examples
/docs
/tests
```

---

## 5. Implementation Phases

# Phase 0 — Preparation and Freeze

## Goal
Freeze the minimum protocol assumptions before coding spreads across repositories.

## Tasks
1. Confirm canonical ACP field names
2. Confirm JSON serialization rules
3. Confirm binary encoding approach (base64)
4. Confirm crypto suite identifiers
5. Confirm direct endpoint and relay endpoint URL patterns
6. Confirm `.well-known` identity document format
7. Confirm `ACK` and `FAIL` reason codes
8. Confirm duplicate-handling rule

## Deliverables
- `protocol-summary.md`
- sample identity document
- sample `SEND` message
- sample `ACK`
- sample `FAIL`

## Exit Criteria
Everyone implementing ACP uses the same message model and encoding assumptions.

---

# Phase 1 — Python Protocol Core

## Goal
Create the core ACP objects and crypto support in Python.

## Tasks
1. Create Python package structure
2. Implement message model classes:
   - routing envelope
   - protected payload
   - wrapped recipient key
3. Implement identity model classes:
   - agent identity
   - identity document
4. Implement key generation utilities
5. Implement signing and verification
6. Implement payload encryption and decryption
7. Implement per-recipient content-key wrapping
8. Implement JSON serialization and parsing
9. Build unit tests for each primitive

## Files / Modules
- `identity.py`
- `identity_doc.py`
- `messages.py`
- `crypto.py`
- `serialization.py`

## Exit Criteria
Python can:
- generate identity
- sign a message
- encrypt payload
- wrap keys for multiple recipients
- serialize/deserialize successfully
- decrypt and verify locally

---

# Phase 2 — Python SDK Skeleton

## Goal
Expose the protocol core through a clean developer-facing API.

## Tasks
1. Implement `Agent.load_or_create()`
2. Implement local key storage strategy
3. Implement identity document creation
4. Implement outbound message builder
5. Implement inbound message parser
6. Implement local direct send via HTTP
7. Implement `ACK` creation
8. Implement `FAIL` creation
9. Implement simple message handler hook
10. Implement deduplication store

## Suggested Public API
```python
from acp import Agent

agent = Agent.load_or_create("agent:test.bot@example.com")

agent.send(
    recipients=["agent:other.bot@example.com"],
    payload={"type": "task_request", "data": {"task": "hello"}},
    context="demo-1"
)
```

## Exit Criteria
One Python agent can send directly to another Python agent using a simple API.

---

# Phase 3 — Direct Delivery Demo

## Goal
Validate ACP without relays first.

## Tasks
1. Create minimal HTTP endpoint for inbound ACP messages
2. Receive incoming envelope
3. Verify signature
4. Decrypt payload
5. Deduplicate by `message_id`
6. Trigger application callback
7. Return `ACK` or `FAIL`
8. Create example script: Python sender → Python receiver

## Exit Criteria
A direct ACP exchange works end-to-end without any relay.

---

# Phase 4 — Discovery

## Goal
Enable identity discovery from domain-like resolution.

## Tasks
1. Implement local cache lookup
2. Implement remote `.well-known` fetch
3. Implement identity document validation
4. Support direct endpoint and relay hints
5. Add TTL / expiration handling
6. Add optional static capability document support
7. Create a test identity-hosting example

## Example Path
```text
https://example.com/.well-known/acp/agents/shipping.bot
```

## Exit Criteria
A sender can resolve a recipient using discovery and then send successfully.

---

# Phase 5 — Python Stateless Relay

## Goal
Build the first ACP relay as a stateless message router.

## Tasks
1. Create relay service skeleton
2. Add HTTP ingress endpoint
3. Validate ACP envelope structure
4. Check message expiry
5. Resolve route from envelope/discovery hints
6. Forward encrypted payload unchanged
7. Add optional short-lived in-memory buffering
8. Add structured logging
9. Add duplicate-tolerant forwarding behavior
10. Add basic health endpoint

## Non-Goals
- durable queue
- persistent ack tracking
- enterprise delivery guarantees

## Exit Criteria
Python agents can communicate through the relay, and duplicate delivery is tolerated.

---

# Phase 6 — Multi-Recipient Messaging

## Goal
Support one logical send to multiple recipients.

## Tasks
1. Add `operation_id` generation
2. Encrypt payload once
3. Wrap CEK for each recipient
4. Track per-recipient result objects
5. Support partial `ACK` / `FAIL`
6. Add `COMPENSATE` message structure
7. Demonstrate one sender to multiple recipients
8. Demonstrate one recipient failure and compensating action emission

## Exit Criteria
ACP supports one-to-many sends in a way that matches the protocol design.

---

# Phase 7 — Capability Advertisement

## Goal
Provide enough capability handling for interoperability.

## Tasks
1. Define capability object structure
2. Publish static capabilities in discovery result or identity metadata
3. Implement optional `CAPABILITIES` message
4. Add sender-side compatibility selection
5. Add structured `FAIL` for mismatches

## Exit Criteria
Sender can evaluate whether recipient supports the required crypto suite and message class.

---

# Phase 8 — Test Vectors and Interoperability Freeze

## Goal
Freeze protocol examples before implementing Java support.

## Tasks
1. Generate sample identity document
2. Generate sample direct-send envelope
3. Generate sample multi-recipient envelope
4. Generate sample `ACK`
5. Generate sample `FAIL`
6. Generate sample `COMPENSATE`
7. Record canonical JSON and encoded field formats
8. Store interop fixtures in `/tests/vectors`

## Exit Criteria
The Java implementation can target stable examples instead of moving behavior.

---

# Phase 9 — Minimal Java ACP Client Library

## Goal
Enable existing Java poker agents to communicate using ACP.

## Tasks
1. Create Java project structure
2. Implement Java model classes:
   - identity
   - identity document
   - message envelope
   - protected payload
3. Implement key loading/generation
4. Implement JSON serialization/parsing
5. Implement Ed25519 signing/verification
6. Implement X25519 key wrapping
7. Implement AES-GCM encryption/decryption
8. Implement direct HTTP and relay HTTP transport
9. Implement `SEND`, `ACK`, `FAIL`
10. Implement lightweight deduplication
11. Validate using stored Python test vectors

## Exit Criteria
Java can send ACP messages compatible with Python and process responses.

---

# Phase 10 — Poker Demo Integration

## Goal
Reuse the existing Java poker dealer and/or player agents over ACP.

## Tasks
1. Identify message points in poker code where Co-operate transport was used
2. Replace transport layer with ACP Java client calls
3. Map poker messages to ACP payloads
4. Support targeted messages for hole cards and action requests
5. Support one-to-many send for broadcasts
6. Support `ACK` / `FAIL`
7. Support partial-failure scenario in demo
8. Validate Java agent ↔ Python agent or Java agent ↔ Java agent via Python relay

## Exit Criteria
Existing poker agents can demonstrate ACP communication convincingly.

---

# Phase 11 — Demo Pack and Developer Docs

## Goal
Package the prototype for demonstration and early developer feedback.

## Tasks
1. Create quick-start guide
2. Create local dev setup guide
3. Create architecture note
4. Create protocol summary
5. Create demo instructions:
   - Python direct
   - Python via relay
   - Java poker demo
6. Create sample identity documents
7. Create sample `.well-known` hosting example
8. Add diagrams where useful

## Exit Criteria
A third party can run the demo with reasonable effort.

---

# Phase 12 — Rust Relay Rewrite Planning

## Goal
Prepare for a drop-in Rust relay without changing protocol semantics.

## Tasks
1. Freeze relay HTTP behavior
2. Freeze forwarding semantics
3. Create relay conformance tests
4. Define relay compatibility requirements
5. Identify Python relay modules to mirror in Rust

## Exit Criteria
The relay can later be rewritten in Rust without changing the SDK or the Java client.

---

## 6. Ordered Task List for Codex

### Batch A — Python Protocol Core
1. Create repository structure for `acp-sdk-python`
2. Implement ACP routing envelope classes
3. Implement ACP protected payload classes
4. Implement identity document classes
5. Implement Ed25519/X25519/AES-GCM helpers
6. Implement JSON serialization utilities
7. Write unit tests for crypto and serialization

### Batch B — Python SDK
8. Implement `Agent.load_or_create()`
9. Implement local key persistence
10. Implement outbound `SEND`
11. Implement inbound processing
12. Implement `ACK`
13. Implement `FAIL`
14. Implement dedup store

### Batch C — Direct Demo
15. Implement minimal inbound HTTP endpoint
16. Add Python sender/receiver demo
17. Validate end-to-end direct delivery

### Batch D — Discovery
18. Implement local cache discovery
19. Implement `.well-known` discovery fetch
20. Validate identity documents
21. Support direct endpoint and relay hints

### Batch E — Relay
22. Create `acp-relay-python`
23. Implement relay ingress route
24. Validate envelope and expiry
25. Forward encrypted messages unchanged
26. Add optional in-memory short buffer
27. Add logging and health checks

### Batch F — Multi-Recipient
28. Add `operation_id`
29. Add multi-recipient CEK wrapping
30. Add per-recipient outcome tracking
31. Add `COMPENSATE` structure
32. Add multi-recipient example

### Batch G — Capabilities and Vectors
33. Add static capabilities
34. Add optional `CAPABILITIES`
35. Add mismatch `FAIL` codes
36. Create protocol test vectors

### Batch H — Java Client
37. Create `acp-sdk-java`
38. Implement Java identity classes
39. Implement Java envelope classes
40. Implement Java crypto helpers
41. Implement Java HTTP transport
42. Implement Java `SEND` / `ACK` / `FAIL`
43. Validate against Python fixtures

### Batch I — Poker Integration
44. Integrate ACP transport into poker dealer
45. Integrate ACP transport into poker players as needed
46. Validate targeted and broadcast poker flows
47. Demonstrate Java ↔ Python interoperability

### Batch J — Demo and Stabilization
48. Create quick-start docs
49. Create local run scripts
50. Stabilize example demos
51. Freeze relay interface for Rust rewrite

---

## 7. Testing Strategy

### Unit Tests
- crypto primitives
- serialization/parsing
- identity document validation
- dedup logic

### Integration Tests
- Python direct send/receive
- Python via relay
- multi-recipient send
- duplicate delivery handling
- failure response handling

### Interoperability Tests
- Python-generated message read by Java
- Java-generated message read by Python
- shared vector validation

### Demo Tests
- poker dealer sends targeted/private message
- poker dealer broadcasts state update
- one recipient fails and compensation is emitted

---

## 8. Key Architecture Decisions to Preserve

The implementation must preserve these decisions:

- relays are stateless by default
- delivery is at-least-once
- recipients deduplicate using `message_id`
- one logical send can target multiple recipients
- payloads are encrypted at protocol layer
- direct communication works without relays
- stateful relays are optional future deployment profile
- event channels are premium future extension

---

## 9. Recommended Immediate Start Prompt for Codex

Use this as the first execution instruction:

> Read the ACP engineering brief and the detailed implementation plan. Start with Batch A and Batch B only. Build the Python ACP SDK core, including message models, identity documents, crypto helpers, serialization, `Agent.load_or_create()`, outbound `SEND`, inbound processing, `ACK`, `FAIL`, and a simple dedup store. Do not implement relay behavior yet. Write tests as you go.

---

## 10. Summary

The implementation path should be:

1. Freeze protocol assumptions
2. Build Python core
3. Prove direct agent-to-agent ACP
4. Add discovery
5. Add stateless relay
6. Add multi-recipient operations
7. Freeze interop vectors
8. Build minimal Java client
9. Reuse poker agents
10. Prepare Rust relay rewrite

This sequencing minimizes risk while maximizing learning and demonstration value.
