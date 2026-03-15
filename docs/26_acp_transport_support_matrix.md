
# ACP Transport Support Matrix

## Purpose

This document summarizes the currently supported ACP transport bindings and their implementation status.

---

## Current Transport Bindings

| Transport | Direct Mode | Relay Mode | Status |
|----------|------------|-----------|--------|
| HTTP | Yes | Yes | Implemented (HTTPS-first + optional mTLS enterprise profile) |
| AMQP | Yes | Yes | Implemented |
| MQTT | Yes | Planned Relay Fallback | Implemented |
| Kafka | No | No | Not Implemented |
| JMS | No | No | Not Implemented |
| P2P | No | No | Not Implemented |

---

## Transport Characteristics

| Transport | Model | Notes |
|----------|------|------|
| HTTP | Direct / Request‑Response | HTTPS-first; optional mTLS profile (`mtls_enabled`); plain HTTP is local/dev/demo exception via explicit override; Java and Python SDKs both support provider-backed TLS/CA material (`local` or `vault`) |
| AMQP | Brokered message routing | RabbitMQ‑compatible |
| MQTT | Directed publish/subscribe | QoS1 at‑least‑once |
| Kafka | Log‑based event stream | Candidate for premium event channels |
| JMS | Enterprise messaging abstraction | Candidate enterprise binding |
| P2P | Peer networking | Long‑term decentralization option |

---

## Transport Invariants

All transport bindings must preserve:

- Canonical ACP message body
- Protocol‑layer encryption
- At‑least‑once delivery
- Duplicate tolerance
- Untrusted intermediary model

Transport metadata must not redefine ACP fields.
