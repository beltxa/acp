# ACP AMQP Interoperability Fixtures Freeze

## Purpose

This document defines the AMQP interoperability fixtures that must be frozen after the first successful ACP-over-AMQP implementation.

The goal is to prevent drift between:

- Python ACP SDK
- Java ACP SDK
- Python relay

These fixtures become the baseline for future transport binding work.

---

## Freeze Rule

Once these fixtures are generated and validated, they should be committed as canonical interoperability artifacts.

Any change to:

- ACP JSON field names
- base64 encoding behavior
- signature coverage
- payload hashing
- wrapped key structure
- AMQP header mirroring
- routing key format

must be treated as a protocol-impacting change and reviewed explicitly.

---

## Required Frozen Fixtures

### 1. Python → Python over AMQP
A Python sender publishes an ACP `SEND` message to an AMQP broker and a Python recipient consumes and processes it.

Artifacts:
- serialized ACP message body
- AMQP headers
- ACK example
- FAIL example

### 2. Java → Python over AMQP
A Java sender publishes an ACP `SEND` message and a Python recipient consumes and processes it.

Artifacts:
- serialized ACP message body
- AMQP headers
- ACK example
- FAIL example

### 3. Python → Java over AMQP
A Python sender publishes an ACP `SEND` message and a Java recipient consumes and processes it.

Artifacts:
- serialized ACP message body
- AMQP headers
- ACK example
- FAIL example

### 4. Multi-Recipient ACP SEND over AMQP
A sender issues one logical ACP operation to multiple recipients and publishes one AMQP message per recipient.

Artifacts:
- per-recipient AMQP message bodies
- routing keys
- per-recipient wrapped keys
- partial ACK / FAIL outcome example
- optional COMPENSATE example

### 5. Duplicate Delivery Fixture
One AMQP message is delivered twice to the same consumer.

Artifacts:
- original message
- duplicate message
- deduplication behavior trace
- expected final processing result

### 6. Relay AMQP Fallback Fixture
The Python relay forwards using AMQP when direct delivery is unavailable.

Artifacts:
- input ACP message
- relay routing decision
- emitted AMQP message
- downstream ACK / FAIL example

Note:
- relay fallback fixtures should use a single-recipient ACP message when asserting exact body equality between relay input and emitted AMQP body.

---

## Fixture Storage Recommendation

Store these under:

```text
/tests/vectors/amqp/
```

Suggested filenames:

```text
python_to_python_send.json
java_to_python_send.json
python_to_java_send.json
multi_recipient_send_B.json
multi_recipient_send_C.json
multi_recipient_send_D.json
duplicate_delivery_case.json
relay_amqp_fallback_case.json
ack_example.json
fail_example.json
```

---

## Fixture Requirements

Each fixture should record:

- ACP version
- message class
- message id
- operation id
- sender
- recipient(s)
- context id
- crypto suite
- serialized body
- transport metadata
- expected result

---

## Canonical Encoding Requirements

The following must remain stable across implementations:

- JSON field names
- JSON structure
- base64 encoding strategy
- binary field placement
- routing key format
- queue naming assumptions where applicable
- ACK and FAIL reason code format

---

## Governance Rule

If a fixture must change, create:

1. a documented rationale
2. a compatibility assessment
3. updated versions for Python and Java
4. regression tests demonstrating intentional compatibility behavior

---

## Outcome

The AMQP fixtures become the reference interoperability baseline for:

- future ACP transport bindings
- new language SDKs
- relay rewrites
- conformance testing
