
# ACP AMQP Transport Binding Specification
Version: Draft v1

## 1. Purpose

This document defines the AMQP transport binding for the Agent Communication Protocol (ACP).

ACP is a transport‑agnostic protocol. This binding specifies how ACP messages are transported through AMQP-compatible systems such as RabbitMQ.

The AMQP binding does not modify ACP protocol semantics. It only defines how ACP messages are carried across AMQP infrastructure.

ACP message payloads remain encrypted and opaque to the AMQP broker.

---

## 2. Scope

This binding defines:

- mapping of ACP messages to AMQP messages
- routing model for ACP agents
- exchange and queue topology
- delivery semantics
- AMQP header usage

This binding does NOT redefine:

- ACP message format
- ACP encryption model
- ACP identity model
- ACP discovery model

---

## 3. AMQP Version

Initial ACP AMQP binding targets:

AMQP 0‑9‑1 (RabbitMQ compatible)

Future versions may add support for:

- AMQP 1.0

---

## 4. ACP Message Carriage

ACP messages are transmitted unchanged inside the AMQP message body.

Example:

AMQP Body = Serialized ACP Message JSON

Example body:

{
  "routing_envelope": {...},
  "protected_payload": {...}
}

---

## 5. Exchange Model

The AMQP broker should expose a direct exchange:

acp.exchange

The exchange receives ACP messages and routes them based on routing keys.

---

## 6. Queue Model

Each ACP agent should have a dedicated queue.

Example:

acp.agent.shipping.bot.companyB

Queue naming format:

acp.agent.<agent_identifier>

---

## 7. Routing Key

Routing key format:

agent.<agent_identifier>

Example:

agent.shipping.bot.companyB

The routing key determines which queue receives the message.

---

## 8. Queue Bindings

Example binding:

Exchange: acp.exchange
Queue: acp.agent.shipping.bot.companyB
Binding Key: agent.shipping.bot.companyB

---

## 9. AMQP Headers

Optional AMQP headers may mirror ACP metadata for routing or observability.

Suggested headers:

acp_version
acp_message_class
acp_message_id
acp_operation_id
acp_sender

These headers are optional and not authoritative.
The canonical protocol message remains inside the message body.

---

## 10. Delivery Semantics

ACP delivery model remains:

at‑least‑once delivery

Implications:

- duplicate messages may occur
- recipients must deduplicate using message_id

AMQP acknowledgement features may be used by consumers but must not alter ACP semantics.

---

## 11. Multi‑Recipient Messaging

When a SEND operation targets multiple recipients:

The sender publishes one AMQP message per recipient.

Example:

Recipients: B, C, D

Publish messages with routing keys:

agent.B
agent.C
agent.D

The encrypted payload remains identical except for wrapped keys.

---

## 12. Security Considerations

AMQP brokers are treated as untrusted infrastructure.

Rules:

- ACP payload encryption must remain intact
- brokers must not decrypt payloads
- brokers only route messages

---

## 13. Discovery Integration

Discovery remains part of ACP discovery mechanisms.

AMQP connection parameters may appear as transport hints in identity documents.

Example:

{
  "transport": {
    "type": "amqp",
    "broker": "amqp.companyB.com",
    "exchange": "acp.exchange"
  }
}

---

## 14. Failure Handling

If a consumer cannot process a message, it should emit an ACP FAIL message.

AMQP-level requeue policies must not override ACP semantics.

---

## 15. Implementation Goal

The first implementation should prioritize:

- RabbitMQ compatibility
- simple routing
- interoperability with Python ACP SDK
- interoperability with Java ACP client
