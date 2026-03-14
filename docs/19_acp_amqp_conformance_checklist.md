# ACP AMQP Conformance Checklist

## Purpose

This checklist is used to confirm that an ACP-over-AMQP implementation conforms to the intended ACP transport binding semantics.

It applies to:

- Python SDK
- Java SDK
- relay behavior when AMQP is used

---

## A. Core ACP Invariants

- [ ] ACP protocol semantics remain unchanged
- [ ] ACP identity model remains unchanged
- [ ] ACP discovery model remains unchanged
- [ ] ACP encryption remains protocol-layer, not broker-layer
- [ ] ACP payload remains opaque to the AMQP broker

---

## B. Message Carriage

- [ ] The complete ACP message is carried in the AMQP message body
- [ ] AMQP body contains the serialized ACP message JSON
- [ ] ACP routing envelope is preserved unchanged
- [ ] ACP protected payload is preserved unchanged
- [ ] Canonical JSON field names are preserved

---

## C. Header Behavior

- [ ] Optional AMQP headers only mirror ACP metadata
- [ ] Headers are not treated as canonical ACP fields
- [ ] Missing AMQP metadata headers do not break ACP processing
- [ ] Header values are consistent with the ACP message body

Suggested mirrored headers:
- [ ] acp_version
- [ ] acp_message_class
- [ ] acp_message_id
- [ ] acp_operation_id
- [ ] acp_sender

---

## D. Routing Model

- [ ] Exchange name is correctly configured
- [ ] Queue naming follows the agreed format
- [ ] Routing key format follows the agreed format
- [ ] One recipient maps to one AMQP publish operation
- [ ] Multi-recipient ACP sends publish one AMQP message per recipient
- [ ] Broker routing does not change ACP semantics

---

## E. Delivery Semantics

- [ ] Delivery semantics remain at-least-once
- [ ] Duplicate delivery is tolerated
- [ ] Recipient deduplicates by message_id
- [ ] Exactly-once semantics are not assumed
- [ ] Broker ack/requeue features do not override ACP semantics

---

## F. Crypto and Security

- [ ] Sender signature verifies correctly after AMQP delivery
- [ ] Payload decrypts correctly after AMQP delivery
- [ ] Wrapped recipient keys remain intact
- [ ] Broker does not require access to decrypted content
- [ ] Broker is treated as untrusted infrastructure

---

## G. Interoperability

- [ ] Python → Python over AMQP works
- [ ] Java → Python over AMQP works
- [ ] Python → Java over AMQP works
- [ ] Multi-recipient AMQP send works
- [ ] ACK and FAIL messages work correctly over AMQP
- [ ] ACK and FAIL are terminal protocol responses (no ACK-of-ACK / FAIL-of-FAIL)
- [ ] Duplicate delivery behavior is correct across languages

---

## H. Relay Behavior

- [ ] Relay can use AMQP as a routing fallback
- [ ] Relay does not alter ACP message body
- [ ] Relay does not decrypt ACP payload
- [ ] Relay preserves recipient routing intent
- [ ] Relay fallback may publish the same canonical ACP body per recipient route when the inbound ACP message is multi-recipient
- [ ] Relay AMQP fallback works when direct delivery is unavailable

---

## I. Error Handling

- [ ] Unsupported message produces ACP FAIL
- [ ] Invalid signature produces ACP FAIL
- [ ] Expired message produces ACP FAIL
- [ ] Unsupported crypto suite produces ACP FAIL
- [ ] Payload-too-large behavior is defined if applicable

---

## J. Final Acceptance

An ACP-over-AMQP implementation is conformant when:

- [ ] all required interop fixtures pass
- [ ] all mandatory checklist items pass
- [ ] duplicate-tolerant behavior is demonstrated
- [ ] ACK and FAIL behavior is demonstrated
- [ ] no ACP invariants are violated
