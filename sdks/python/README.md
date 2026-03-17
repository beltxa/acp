# ACP — Agent Communication Protocol

ACP (Agent Communication Protocol) is a secure, identity-driven protocol for autonomous systems to communicate, collaborate, and coordinate across environments.

Unlike traditional API integrations or message brokers, ACP is designed for **AI agents** operating in dynamic, distributed ecosystems.

This project is not related to other packages using the acronym "ACP"

---

## What is ACP?

ACP provides:

- Identity-first communication between agents
- Signed and optionally encrypted message envelopes
- Transport independence (HTTP, AMQP, MQTT)
- Relay-based routing across network boundaries
- Capability-driven interaction patterns

This enables agents to discover each other, exchange messages, and collaborate without tight coupling.

---

## Why ACP?

Modern systems are evolving from services into **autonomous agents**.

Current approaches (REST APIs, webhooks, point-to-point messaging) lead to:

- brittle integrations
- hidden coupling
- limited interoperability
- lack of governance

ACP introduces a **protocol layer** for agent communication, similar to how HTTP enabled the web.

---

## Getting Started

```bash
pip install acp-runtime
pip install acpctl
acp identity create
acp message send agent:demo ping