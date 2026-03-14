# ACP Ecosystem Diagram

## Conceptual Architecture

```text
           Autonomous Agents
                 │
          ┌──────┴──────┐
          │   ACP SDK   │
          └──────┬──────┘
                 │
         Identity & Discovery
                 │
        ┌────────┴─────────┐
        │                  │
   Direct Communication   Relay Network
        │                  │
        └──────┬───────────┘
               │
         Transport Layer
               │
   HTTP   AMQP   MQTT   Kafka   P2P
               │
        Enterprise Layer
     (Governance / Compliance)
```

## Key Properties

Agents may communicate:

- directly
- through relays
- through transport systems

The protocol layer remains unchanged regardless of transport.

---

## Layer Responsibilities

### Agents
Autonomous systems performing tasks and interacting with other agents.

### ACP SDK
Implements protocol logic:

- encryption
- message construction
- discovery
- transport selection

### Discovery & Identity
Allows agents to locate each other and verify identities.

### Relay Network
Optional infrastructure that forwards encrypted messages.

### Transport Layer
Underlying communication systems used to carry ACP messages.

### Enterprise Layer
Optional services providing:

- governance
- compliance
- reliability guarantees
