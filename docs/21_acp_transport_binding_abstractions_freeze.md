# ACP Transport Binding Abstractions Freeze

## Purpose

This document freezes the common abstraction model for ACP transport bindings.

The goal is to ensure that new bindings such as:

- HTTP direct
- HTTP relay
- AMQP
- MQTT
- Kafka
- P2P
- JMS

all preserve ACP semantics instead of redesigning the protocol each time.

---

## Core Rule

A transport binding carries ACP messages.

A transport binding does not redefine:

- ACP identity
- ACP discovery
- ACP encryption
- ACP message semantics
- ACP delivery model assumptions

---

## Frozen Abstraction Layers

### Layer 1 — ACP Core
Unchanged across all bindings:
- routing envelope
- protected payload
- identity model
- discovery model
- message classes
- crypto model

### Layer 2 — Transport Binding
Binding-specific mapping:
- addressing
- message carriage
- routing hints
- transport metadata
- delivery mechanics

### Layer 3 — Deployment Profile
Optional operational model:
- direct
- relay-assisted
- stateful enterprise relay
- premium event-channel profile later

---

## Binding Responsibilities

Each transport binding must define:

1. How ACP messages are carried
2. How recipients are addressed at transport level
3. How delivery occurs
4. How duplicates are handled
5. How transport-specific metadata is used
6. How discovery advertises transport hints
7. How ACP failures are represented in the transport context

---

## Binding Invariants

Every ACP transport binding must preserve:

- ACP message body remains authoritative
- payload encryption remains protocol-layer
- at-least-once delivery assumption unless explicitly profiled otherwise
- duplicate tolerance at recipient
- recipient deduplication by ACP `message_id`
- sender/recipient identity semantics unchanged
- broker/router infrastructure treated as untrusted unless separately profiled
- `ACK` and `FAIL` as terminal protocol responses (no auto ACK/FAIL response loops)

---

## Canonical Binding Questions

Every new transport binding must answer:

1. What transport is being bound?
2. What role does it play? (direct, relay, fallback, brokered path)
3. What object carries the ACP message?
4. What transport metadata is mirrored from ACP?
5. How are recipients addressed?
6. How is one-to-many send represented?
7. What delivery guarantees are assumed?
8. How are duplicates handled?
9. How is discovery integrated?
10. What does the transport not change?

---

## Shared Implementation Abstraction

SDKs should converge on a common transport interface.

Conceptual interface:

```python
class TransportAdapter:
    def send(acp_message, recipient_hints): ...
    def receive(): ...
    def supports(capability): ...
```

Equivalent abstractions should exist in Java and other SDKs.

The key point is not exact syntax, but a stable transport-adapter concept.

---

## Discovery Integration Rule

Discovery may advertise transport hints such as:

- direct HTTP endpoint
- relay endpoint
- AMQP broker and exchange
- future MQTT broker/topic hints
- future Kafka topic hints

But transport hints do not replace ACP identity or trust semantics.

---

## Response Path Determination

Transport bindings must define a deterministic response path for protocol responses such as:
-	ACK
-	FAIL
-	COMPENSATE (when used)

When a response is generated, the recipient should determine the sender return path using the following order:
1.	Sender transport hint for the same transport
2.	Sender preferred transport hints
3.	Agent channel selection policy

Example:

If a message arrives via MQTT and the sender identity includes:
{
  "service": {
    "mqtt": {
    "broker": "mqtt.companyA.com",
    "topic": "acp/agent/sender"
    }
  }
}

Then responses should be sent using the sender’s service.mqtt transport hint.

Transport bindings must not invent implicit response paths.

## Non-Goals

The abstraction freeze does not define:
- premium event channels
- enterprise-specific policy controls
- billing or commercial routing rules
- exactly-once delivery semantics

---

## Outcome

Future transport bindings should be created by instantiating this abstraction model instead of redefining ACP each time.
