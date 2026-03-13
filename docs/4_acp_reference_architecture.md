
# ACP Reference Architecture

## Overview

The ACP reference architecture describes how agents, SDKs, relays, and discovery services interact.

ACP is structured in three layers:

1. Protocol Layer (ACP specification)
2. Network Layer (relay infrastructure and discovery)
3. Enterprise Layer (governance, compliance, policy)

---

## High-Level Architecture

```mermaid
flowchart TB

    subgraph Agents
        A1[Agent A]
        A2[Agent B]
        A3[Agent C]
    end

    subgraph SDK
        SDK1[ACP SDK]
        SDK2[ACP SDK]
        SDK3[ACP SDK]
    end

    subgraph Network
        R1[Relay Node]
        R2[Relay Node]
        D[Discovery Service]
    end

    subgraph Enterprise
        G[Governance Layer]
        C[Compliance Layer]
        P[Policy Engine]
    end

    A1 --> SDK1
    A2 --> SDK2
    A3 --> SDK3

    SDK1 --> R1
    SDK2 --> R1
    SDK3 --> R2

    R1 --> R2
    R1 --> D

    R2 --> G
    G --> C
    C --> P
```

---

## Component Responsibilities

### Agents
Autonomous software entities that perform tasks and communicate using ACP.

### ACP SDK
Handles protocol operations:

- encryption
- identity management
- discovery
- routing
- delivery state tracking

### Relay Nodes
Forward encrypted messages between agents.

Responsibilities:

- envelope validation
- routing
- optional store-and-forward

Relays must never decrypt payloads.

### Discovery Service
Resolves agent identifiers into identity documents and reachability hints.

### Enterprise Layer
Optional enterprise services providing:

- governance
- compliance logging
- policy enforcement
- regulated identity frameworks

---

## Message Flow Example

```mermaid
sequenceDiagram
    participant A as Agent A
    participant S as ACP SDK
    participant R as Relay
    participant B as Agent B

    A->>S: send()
    S->>R: ACP message
    R->>B: forward
    B->>R: ACK
    R->>S: ACK
```

---

## Design Goals

- secure end-to-end communication
- infrastructure optionality
- decentralized discovery
- extensibility for enterprise use
