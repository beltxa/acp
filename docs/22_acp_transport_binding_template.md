# ACP Transport Binding Template

## Document Purpose

Use this template to define a new ACP transport binding while preserving ACP core invariants.

---

# ACP <TRANSPORT> Transport Binding Specification
Version: Draft v1

## 1. Purpose

This document defines the <TRANSPORT> transport binding for the Agent Communication Protocol (ACP).

ACP is transport-agnostic. This binding specifies how ACP messages are transported through <TRANSPORT> infrastructure.

The binding does not modify ACP semantics.

---

## 2. Scope

This binding defines:

- mapping of ACP messages to <TRANSPORT> messages
- addressing model
- routing model
- delivery semantics
- transport metadata usage

This binding does not redefine:

- ACP identity
- ACP discovery
- ACP encryption
- ACP message semantics

---

## 3. Transport Version / Target

Initial target:

- <TRANSPORT VERSION OR PLATFORM>

Future targets:

- <OPTIONAL FUTURE TARGETS>

---

## 4. ACP Message Carriage

Define how the ACP message is carried by the transport.

Questions to answer:

- Is the full ACP message the message body?
- Is the ACP message split across fields?
- Which object is authoritative?

Rule:
The ACP message body should remain canonical unless there is a very strong reason otherwise.

---

## 5. Addressing Model

Define how ACP recipients are addressed using <TRANSPORT>.

Examples:
- routing key
- topic
- queue
- endpoint
- peer address

---

## 6. Routing / Topology Model

Define how messages move through the transport.

Examples:
- direct
- brokered
- pub/sub
- relay fallback
- peer-to-peer

---

## 7. Transport Metadata

Define any transport-specific metadata that may mirror ACP information.

Examples:
- headers
- properties
- topic attributes

Rule:
Transport metadata is optional and non-canonical unless explicitly stated.

---

## 8. Delivery Semantics

State the delivery model.

Questions:
- at-least-once?
- duplicates possible?
- ordering guarantees?
- retry behavior?

ACP default assumption:
- at-least-once
- duplicate-tolerant recipient behavior
- recipient deduplication by `message_id`
- `ACK` / `FAIL` are terminal protocol responses (no ACK-of-ACK / FAIL-of-FAIL loops)

---

## 9. Multi-Recipient Handling

Define how one ACP logical send to multiple recipients is represented in this transport.

Examples:
- one transport message per recipient
- one publish with multiple subscriptions
- repeated direct send

---

## 10. Security Considerations

State clearly:

- transport does not replace ACP encryption
- intermediaries are untrusted unless profiled otherwise
- payload remains encrypted end-to-end

---

## 11. Discovery Integration

Define how transport hints appear in ACP discovery.

Transport hints should be carried as non-canonical identity-service hints (for example under `service.<transport>`), not as replacements for ACP identity or trust semantics.

Examples:
- broker address
- topic namespace
- queue name pattern
- peer bootstrap hints

---

## 12. Failure Handling

Define how ACP FAIL interacts with the transport.

Questions:
- is transport-level retry allowed?
- what happens on requeue or redelivery?
- how are ACP failures surfaced?
- how are terminal `ACK`/`FAIL` responses handled without response loops?

---

## 13. Implementation Goal

Describe the first implementation target.

Examples:
- RabbitMQ-compatible AMQP
- MQTT 5 broker
- Kafka topic-based transport
- direct libp2p peer transport

---

## 14. Out of Scope

List what this first binding version does not include.

---

## 15. Conformance Checklist

List concrete checks for:
- preserved ACP invariants
- transport carriage correctness
- interop behavior
- duplicate handling
- ACK / FAIL behavior
