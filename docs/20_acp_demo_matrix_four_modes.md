# ACP Demo Matrix – Chess and Poker in Four Modes

## Purpose

This document defines the recommended demonstration matrix now that ACP supports:

- direct delivery
- relay delivery
- AMQP transport binding

The goal is to show that ACP is:

- protocol-driven
- language-independent
- transport-extensible
- not dependent on a single routing model

---

## Four Demonstration Modes

### Mode 1 — Direct HTTP
Agents communicate directly without a relay.

### Mode 2 — Via Relay
Agents communicate through the ACP relay using HTTP transport.

### Mode 3 — Direct AMQP
Agents communicate via AMQP transport binding without relying on relay routing behavior.

### Mode 4 — Relay with AMQP Fallback
Agents use the relay, and the relay falls back to AMQP when direct delivery is unavailable.

---

## Chess Demo Matrix

### Chess Mode 1 — Direct HTTP
Goal:
- prove one-to-one ACP direct communication

Expected flow:
- Chess Agent A sends move to Chess Agent B
- Chess Agent B verifies, decrypts, ACKs
- State updates remain correct

Validation points:
- direct discovery/config works
- direct HTTP transport works
- ACK path works
- duplicate tolerance can be demonstrated separately

### Chess Mode 2 — Via Relay
Goal:
- prove one-to-one ACP communication through relay

Expected flow:
- Chess Agent A sends to relay
- Relay forwards to Chess Agent B
- Chess Agent B ACKs

Validation points:
- relay forwarding works
- payload remains encrypted
- relay can remain untrusted

### Chess Mode 3 — Direct AMQP
Goal:
- prove one-to-one ACP communication over AMQP binding

Expected flow:
- Chess Agent A publishes ACP message to AMQP
- Chess Agent B consumes and processes
- ACK is generated

Validation points:
- AMQP binding works
- routing key and queue model work
- broker remains transport only

### Chess Mode 4 — Relay with AMQP Fallback
Goal:
- prove relay can route via AMQP when direct delivery is unavailable

Expected flow:
- direct delivery unavailable
- relay emits ACP message via AMQP
- Chess Agent B receives through AMQP
- ACK returned

Validation points:
- relay transport fallback works
- ACP semantics remain unchanged

---

## Poker Demo Matrix

### Poker Mode 1 — Direct HTTP
Goal:
- prove many-to-many ACP direct communication without relay

Expected flow:
- dealer sends targeted hole cards
- dealer sends targeted action requests
- dealer sends one-to-many public updates
- players respond directly

Validation points:
- one-to-one targeted messages work
- one-to-many direct messages work
- multi-recipient ACP intent works without relay

### Poker Mode 2 — Via Relay
Goal:
- prove many-to-many ACP communication through relay

Expected flow:
- dealer sends via relay
- relay forwards targeted and broadcast-like messages
- players respond via relay or direct return path

Validation points:
- relay can support many-to-many ACP flow
- targeted privacy remains intact
- payload remains encrypted end-to-end

### Poker Mode 3 — Direct AMQP
Goal:
- prove many-to-many ACP communication over AMQP binding

Expected flow:
- dealer publishes one AMQP message per recipient
- players consume targeted messages
- public updates sent as multiple routed messages
- ACK / FAIL behavior visible

Validation points:
- one logical operation can produce multiple AMQP publishes
- duplicate-tolerant behavior remains correct
- Java and Python interop remains intact if mixed implementations are used

### Poker Mode 4 — Relay with AMQP Fallback
Goal:
- prove mixed routing and broker-backed delivery in a more realistic topology

Expected flow:
- relay attempts direct path
- fallback to AMQP where required
- players receive targeted and public messages
- dealer observes outcomes

Validation points:
- ACP remains coherent across routing modes
- relay fallback does not alter semantics
- many-to-many communication still works

---

## Recommended Demonstration Order

1. Chess Mode 1
2. Chess Mode 2
3. Chess Mode 3
4. Chess Mode 4
5. Poker Mode 1
6. Poker Mode 2
7. Poker Mode 3
8. Poker Mode 4

This order gives:
- simplest proof first
- routing proof second
- transport binding proof third
- combined routing + transport proof fourth

---

## Suggested Evidence to Capture

For each demo mode capture:

- topology diagram
- sender/recipient identities
- transport used
- example ACP message ids
- ACK / FAIL traces
- duplicate handling evidence if relevant
- screenshots or logs
- short narrative of what the demo proves

---

## Strategic Value

If all eight demonstrations work, ACP can be shown as:

- a real protocol, not just a library
- language-independent
- direct-capable
- relay-capable
- transport-extensible
- suitable for both one-to-one and many-to-many scenarios
