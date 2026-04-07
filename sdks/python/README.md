## ACP — Agent Communication Protocol - version 0.1.6
ACP (Agent Communication Protocol) is a secure, identity-driven protocol for autonomous systems to communicate, collaborate, and coordinate across environments.
Unlike traditional API integrations or message brokers, ACP is designed for AI agents operating in dynamic, distributed ecosystems.
This project is not related to other packages using the acronym "ACP"

**HTTP is for services. ACP is for agents.**

## What is ACP?

ACP provides:
- Identity-first communication between agents
- Signed and optionally encrypted message envelopes
- Transport independence (HTTP, AMQP, MQTT)
- Relay-based routing across network boundaries
- Capability-driven interaction patterns

This enables agents to discover each other, exchange messages, and collaborate without tight coupling.
ACP SDKs across languages are interoperable and implement the same protocol semantics.

## What ACP Is Not

- Not a message broker.
- Not a JSON schema format.
- Not a framework-specific tool protocol.

## Why ACP?
Modern systems are evolving from services into autonomous agents.
Current approaches (REST APIs, webhooks, point-to-point messaging) lead to:
- brittle integrations
- hidden coupling
- limited interoperability
- lack of governance

ACP introduces a protocol layer for agent communication, similar to how HTTP enabled the web.

## When to Use ACP

Use ACP when:

- autonomous agents need to communicate across teams, runtimes, or network boundaries
- identity and message verification are required at the protocol level
- you want one protocol across direct and relay delivery paths

ACP may be unnecessary when:

- one application calls one service with stable, tightly controlled APIs
- plain HTTP/REST already solves the integration with low coordination overhead

## ACP vs Typical Approaches

| Approach | Good fit | Gaps for autonomous agent communication |
| --- | --- | --- |
| REST APIs | stable service-to-service calls | endpoint coupling and custom identity/discovery conventions |
| Webhooks | event callbacks | delivery and trust rules vary by implementation |
| Message brokers | high-throughput internal messaging | broker-specific semantics, no shared agent protocol layer |
| Agent tool protocols | tool invocation inside one framework | often framework-scoped, not cross-runtime protocol contracts |
| ACP | cross-agent protocol with identity + secure envelopes | adds protocol concepts not needed for trivial single-service cases |

## SDK Installation Parity

Status labels used in this repo:
- `Published`
- `Available from repo`
- `Experimental`
- `Bridge-based`
- `Coming`

| SDK | Status |
| --- | --- |
| Python (`acp-runtime`) | `Published`|
| TypeScript (`acp-runtime`) | `Published`|
| Rust (`acp-runtime`) | `Published`|
| Go (`github.com/beltxa/acp/sdks/go`) | `Available from repo`|
| Java (`tech.co-operate:acp-runtime`) | `Published` |
| Mojo wrapper (`acp-sdk-mojo`) | `Bridge-based` |

No SDK in this repository snapshot is currently labeled `Coming`.

## Repo Structure

- `getting-started/`: verified local ping flow
- `examples/`: runnable demos (`hello_world_agent.py`, one-to-one, one-to-many, capabilities)
- `sdks/`: language SDK implementations
- `cli/`: ACP CLI (`acp`)
- `relay-dev/`: developer relay for local/test routing

## Open Source Scope

This repository is for learning, local development, and interoperability testing.

---
## Install

Published package:

```bash
pip install acp-runtime
```

From this repository:

```bash
pip install -e sdks/python
```

## Minimal demo

Canonical single-file Hello World:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python
python examples/hello_world_agent.py
```

Fast local ping flow:

```bash
./getting-started/quickstart_ping.sh
```

## SDK capabilities

- create/load agent identities
- sign and verify identity documents
- build and send ACP messages over direct or relay paths
- request and compare agent capabilities
- use HTTP, AMQP, and MQTT transports

### v0.1.0 : Initial release - Unstable
### v0.1.1 : Bug Fixing
### v0.1.2 : Bug Fixing
### v0.1.3 : Bug Fixing
### v0.1.4 : First stable release
### v0.1.5 : Introduced concept of "tenant" to allow differentiation of multiple agents with the same name
### v0.1.6 : Renamed "tenant" to "namespace" for clarity. Added transport authentication specifications