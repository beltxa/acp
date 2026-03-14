# ACP MQTT Transport Binding Specification
Version: Draft v1

## 1. Purpose

This document defines the MQTT transport binding for the Agent Communication Protocol (ACP).

ACP is transport-agnostic. This binding specifies how ACP messages are transported through MQTT-compatible brokers.

The MQTT binding does not modify ACP protocol semantics.

MQTT is used only as a transport binding for ACP messages.

---

## 2. Scope

This binding defines:

- mapping of ACP messages to MQTT publishes
- topic model for ACP routing
- delivery semantics
- MQTT metadata usage
- discovery transport hints

This binding does not redefine:

- ACP identity
- ACP discovery
- ACP encryption
- ACP message semantics

---

## 3. Transport Target

Initial target:

- MQTT 5 broker-compatible implementation

Future targets may include:
- broader MQTT 3.x compatibility if needed

---

## 4. ACP Message Carriage

The full serialized ACP message is carried in the MQTT message payload.

```text
MQTT payload = ACP message JSON
```

The ACP message body remains canonical.

---

## 5. Addressing Model

MQTT topics are used as the transport addressing layer.

Recommended topic format for directed ACP delivery:

```text
acp/agent/<agent_identifier>
```

Example:

```text
acp/agent/shipping.bot.companyB
```

A recipient agent subscribes to its own topic.

`<agent_identifier>` should use a stable token derived from ACP `agent:<name>@<domain>`:
- start with `<name>` if no domain, otherwise `<name>.<domain>`
- replace non `[a-zA-Z0-9._-]` characters with `.`
- collapse repeated `.`, trim leading/trailing `.`

---

## 6. Routing / Topology Model

For v1, MQTT binding is defined as a directed message transport, not as an event-channel profile.

That means:
- sender publishes to recipient topic
- recipient subscribes to its own topic
- broker routes based on topic subscription
- ACP retains message-router semantics

This is important because premium event channels are explicitly out of scope for core ACP.

---

## 7. MQTT Metadata

Optional MQTT properties may mirror ACP metadata.

Suggested mirrored values:
- acp_version
- acp_message_class
- acp_message_id
- acp_operation_id
- acp_sender

These are optional and non-canonical.

The canonical protocol message remains the ACP message in the payload.

---

## 8. Delivery Semantics

MQTT binding must preserve ACP assumptions:

- at-least-once delivery
- duplicate messages are possible
- recipient deduplicates using `message_id`

Recommended starting QoS:
- QoS 1 for practical at-least-once behavior

MQTT QoS must not be interpreted as changing ACP semantics to exactly-once.

---

## 9. Multi-Recipient Handling

For a multi-recipient ACP SEND:

- publish one MQTT message per recipient topic
- each MQTT publish carries an ACP message whose envelope `recipients` contains only the target recipient
- each published ACP message includes only the target recipient wrapped key material for that publish

Example:

Recipients:
- B
- C
- D

Publishes:
- acp/agent/B
- acp/agent/C
- acp/agent/D

This preserves ACP multi-recipient intent while keeping directed routing explicit.

---

## 10. Security Considerations

MQTT broker is treated as untrusted transport infrastructure.

Rules:
- ACP payload encryption remains intact
- broker must not decrypt payload
- topic routing does not replace ACP identity
- MQTT TLS is useful but does not replace ACP protocol-layer security

---

## 11. Discovery Integration

MQTT transport hints may appear in ACP discovery metadata under identity service hints.

Recommended hint placement:

```json
{
  "service": {
    "mqtt": {
      "broker_url": "mqtt://mqtt.companyB.com",
      "topic": "acp/agent/shipping.bot.companyB",
      "qos": 1
    }
  }
}
```

Discovery still remains ACP discovery.

---

## 12. Failure Handling

If a recipient cannot process a message, it should emit ACP FAIL.

`ACK` and `FAIL` are terminal protocol responses. Implementations must not auto-emit
`ACK`/`FAIL` in response to incoming `ACK`/`FAIL`.

MQTT broker redelivery or reconnect behavior must not override ACP-level semantics.

---

## 13. Implementation Goal

The first MQTT binding implementation should prioritize:

- MQTT 5 compatibility
- simple directed topic routing
- interoperability with Python and Java ACP SDKs
- duplicate-tolerant recipient processing

---

## 14. Topic normalization rules:

To ensure interoperability across implementations, MQTT topic derivation from ACP agent identifiers must be deterministic.

1.	Use a fixed prefix:

    acp/agent/

2.	Normalize the ACP agent identifier:

Example:
    agent:shipping.bot@companyB

Normalized topic:

    acp/agent/shipping.bot.companyB

Normalization rules:
•	remove agent: prefix
•	replace @ with .
•	convert to lowercase
•	disallow wildcard characters
•	avoid broker-reserved characters

Both Python and Java implementations must use the same normalization algorithm.

## 15. Out of Scope

This binding does not yet include:

- premium event channels
- wildcard-based collaborative topics
- shared-subscription group semantics
- exactly-once ACP semantics
- broker-side content inspection

---

## 16. Conformance Checklist

- [ ] ACP message remains canonical in MQTT payload
- [ ] topic addressing preserves directed ACP routing
- [ ] recipient deduplicates by message_id
- [ ] QoS does not change ACP semantics
- [ ] broker never decrypts payload
- [ ] multi-recipient sends publish one message per recipient
- [ ] each directed publish uses a single-recipient ACP envelope and recipient-specific wrapped key material
- [ ] ACK and FAIL flows work correctly over MQTT
- [ ] ACK and FAIL are treated as terminal responses (no ACK-of-ACK / FAIL-of-FAIL)
