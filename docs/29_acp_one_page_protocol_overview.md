# ACP One-Page Protocol Overview

## What ACP Is
The **Agent Communication Protocol (ACP)** is a secure, transport-agnostic protocol designed for communication between autonomous software agents across organizations and networks.

ACP provides a standard way for agents to:

- discover each other
- authenticate identity
- exchange encrypted messages
- coordinate tasks
- tolerate duplicate delivery
- communicate over multiple transports

ACP works over:

- direct HTTP
- relays
- AMQP
- MQTT
- future transports (Kafka, P2P, JMS)

ACP messages remain encrypted end-to-end and are transport-independent.

---

## Core Principles

1. **Protocol First**  
   ACP defines how agents communicate, not how infrastructure must be deployed.

2. **Transport Agnostic**  
   ACP runs over existing transports instead of replacing them.

3. **Infrastructure Optional**  
   Agents can communicate directly without relays.

4. **Duplicate-Tolerant**  
   ACP assumes at-least-once delivery and builds resilience into the protocol.

5. **Language Independent**  
   Multiple SDKs can implement ACP (Python, Java, etc.).

---

## Why ACP Exists

Today most agent systems communicate using:

- HTTP APIs
- webhooks
- ad-hoc message queues

This leads to:

- brittle integrations
- vendor lock-in
- fragile network topologies
- lack of security and identity standards

ACP introduces a **standard communication layer for agents**.

---

## What Makes ACP Different

ACP separates:

- Protocol
- Network Infrastructure
- Enterprise Governance

This allows:

- open protocol adoption
- flexible infrastructure choices
- monetizable enterprise services

---

## Current Implementation Status

ACP currently includes:

- Python SDK
- Java SDK
- stateless relay
- AMQP binding
- MQTT binding
- working demos (chess + poker)

ACP has already demonstrated:

- one-to-one communication
- many-to-many communication
- cross-language interoperability
- multiple transport bindings
