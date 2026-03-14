
# ACP Demo Readiness Checklist

## Purpose

This checklist ensures that ACP demonstrations are reproducible and ready for external presentation.

---

## Chess Demonstrations

| Mode | Status |
|-----|-------|
| Direct HTTP | Complete |
| Via Relay | Complete |
| Direct AMQP | Complete |
| Direct MQTT | Complete |

Validation points:

- One‑to‑one message flow
- Encrypted payload verification
- ACK responses
- Duplicate tolerance

---

## Poker Demonstrations

| Mode | Status |
|-----|-------|
| Direct HTTP | Complete |
| Via Relay | Complete |
| Direct AMQP | Complete |
| Direct MQTT | Complete |

Validation points:

- Targeted hole‑card messages
- Broadcast game state updates
- Multi‑recipient sends
- ACK/FAIL responses

---

## Demo Evidence

For each demo mode capture:

- topology diagram
- transport type
- sender/recipient identities
- example message IDs
- ACK/FAIL traces
- duplicate handling logs

---

## Demo Preparation Tasks

- Provide quick‑start scripts
- Provide Docker or local run instructions
- Provide minimal identity documents
- Provide example discovery setup
- Include screenshots or logs

---

## Success Criteria

ACP demonstrations should clearly show:

- protocol‑driven messaging
- cross‑language interoperability
- transport flexibility
- direct and relay communication
- both one‑to‑one and many‑to‑many agent interaction
