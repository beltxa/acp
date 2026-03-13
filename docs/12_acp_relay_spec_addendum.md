
# ACP Relay Specification Addendum
## Stateless Relay Model and Stateful Relay Profile

### Purpose

This addendum extends the ACP Relay Specification to clarify the relay operational model.

ACP relays are defined as stateless by default, with an optional stateful relay profile for enterprise deployments.

---

# 1. Stateless Relay Model (Default)

## Overview

In the default ACP deployment model, relays act as lightweight message routers.

Responsibilities:

- receive ACP messages
- validate routing envelope structure
- check message expiration
- determine next hop or recipient
- forward encrypted message payloads

Relays must not decrypt payloads.

Relays do not maintain durable delivery state.

---

# 2. Delivery Semantics

ACP uses at-least-once delivery semantics.

Implications:

- relays may forward the same message multiple times
- duplicate deliveries are possible
- recipients must deduplicate messages using `message_id`
- agents must tolerate replay-safe processing

Recipients should track processed message identifiers to prevent duplicate execution.

---

# 3. Multi-Path Routing

Relays may forward messages through multiple possible routes.

Example:

Agent A → Relay A → Relay B → Agent B  
Agent A → Relay C → Relay B → Agent B

Multi-path routing improves network resilience.

Agents should treat duplicate deliveries as normal behavior.

---

# 4. Stateless Relay Characteristics

Stateless relays typically:

- hold messages only briefly in memory
- do not maintain persistent queues
- do not track delivery acknowledgements
- do not perform retry orchestration

Stateless relay implementations are expected to be simple and lightweight.

---

# 5. Optional In-Memory Buffering

Relays may optionally perform short-lived buffering for transient network delays.

Example uses:

- temporary backpressure handling
- small retry windows
- batching or load smoothing

This buffering must not be relied upon for durable delivery guarantees.

---

# 6. Stateful Relay Profile (Optional)

ACP supports a stateful relay deployment profile.

Stateful relays may include:

- durable message queues
- store-and-forward delivery
- delivery acknowledgement tracking
- retry scheduling
- operational monitoring

Stateful relays are typically used in:

- enterprise deployments
- internal organizational networks
- regulated environments

---

# 7. Security Considerations

Both stateless and stateful relays:

- must not decrypt ACP payloads
- must treat payloads as opaque encrypted blobs
- must validate routing envelopes
- should enforce message size limits and expiration

Payload confidentiality remains guaranteed by ACP message encryption.

---

# 8. Implementation Guidance

For the ACP reference implementation:

- stateless relay should be implemented first
- relay must support envelope validation and forwarding
- duplicate deliveries should be allowed
- SDK must implement deduplication logic

Stateful relay implementations may be developed later as enterprise extensions.

---

# 9. Design Goal

The stateless-first model ensures:

- minimal relay complexity
- low infrastructure barriers
- strong resilience in distributed networks
- compatibility with enterprise-grade deployments when required
