
# ACP Transport Invariants

Version: Draft v1

## Purpose

This document captures critical transport-layer invariants that must remain consistent
across all ACP transport bindings and across all SDK implementations (Python, Java,
and future languages).

These rules prevent subtle interoperability bugs that may arise when ACP is carried
over different transport systems such as:

- HTTP (direct)
- HTTP (relay)
- AMQP
- MQTT
- Kafka
- P2P
- JMS

Transport bindings must follow these invariants unless explicitly superseded by a
future ACP protocol revision.

---

# 1. Response Path Determination

ACP protocol responses include:

- `ACK`
- `FAIL`
- `COMPENSATE` (when applicable)

When generating a response, the recipient must determine the sender return path
using the following precedence order.

### Response Transport Selection Order

1. **Sender transport hint for the same transport**
2. **Sender preferred transport hints**
3. **Agent channel selection policy fallback**

Example identity transport hint:

```json
{
  "service": {
    "mqtt": {
      "broker": "mqtt.companyA.com",
      "topic": "acp/agent/sender"
    }
  }
}
```

If a message was received via MQTT and the sender advertises a `service.mqtt`
hint, responses should be returned through MQTT.

Transport bindings must not invent implicit response paths.

---

# 2. Topic / Address Normalization

Transport bindings that derive routing addresses from ACP agent identifiers must
use deterministic normalization rules.

This ensures interoperability across SDK implementations.

Example ACP identifier:

```
agent:shipping.bot@companyB
```

Normalized transport address example (MQTT topic):

```
acp/agent/shipping.bot.companyb
```

### Normalization Rules

1. Remove `agent:` prefix
2. Replace `@` with `.`
3. Convert identifier to lowercase
4. Disallow wildcard characters
5. Avoid broker-reserved characters
6. Apply the same transformation in every SDK implementation

---

# 3. Canonical Message Body Rule

For all transport bindings:

- The **ACP message JSON is the canonical payload**
- Transport metadata must never replace or redefine ACP fields

Example:

```
Transport Payload = ACP JSON Message
```

Transport headers or metadata may mirror ACP metadata but must not be treated
as authoritative protocol fields.

---

# 3.1 HTTP Transport Security Posture

For HTTP-based ACP paths (direct agent HTTP, relay HTTP, discovery/registration HTTP):

- `https://` is the default recommendation
- plain `http://` is allowed only as an explicit local/dev/demo exception
- this transport hardening does not change ACP payload encryption semantics

---

# 4. Delivery Semantics

All ACP transport bindings must preserve:

```
at-least-once delivery
```

Implications:

- duplicate delivery is possible
- recipients must deduplicate using `message_id`
- exactly-once delivery must not be assumed

---

# 5. Broker / Intermediary Trust Model

Transport intermediaries such as:

- relays
- brokers
- routers

must be treated as **untrusted infrastructure**.

Requirements:

- ACP payload encryption must remain intact
- intermediaries must not decrypt ACP payloads
- intermediaries must only route messages

---

# 6. Multi-Recipient Messaging

For multi-recipient `SEND` operations:

Transport bindings should represent the operation as:

```
one transport message per recipient
```

Each transport message contains:

- the same encrypted payload
- the recipient-specific wrapped key

This ensures routing remains deterministic.

---

# 7. Cross-Language Consistency

All SDK implementations must follow identical rules for:

- JSON serialization
- binary encoding (base64)
- signature verification
- payload hashing
- key wrapping format
- address normalization

Frozen interoperability fixtures should be used to verify compatibility.

---

# 8. Governance Rule

Any change to the following requires explicit ACP protocol review:

- message serialization format
- transport normalization rules
- response path determination
- delivery semantics
- encryption envelope structure

Changes to these invariants affect interoperability across languages and
transport bindings.

---

# Summary

These transport invariants ensure that ACP remains:

- protocol-driven
- language-independent
- transport-extensible
- interoperable across SDK implementations
