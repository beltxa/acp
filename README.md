# ACP — Agent Communication Protocol

**The HTTP of AI agents**

ACP is a secure, identity-driven protocol for autonomous systems to communicate,
collaborate, and coordinate across organizations.

---

## Why ACP?

Modern systems are evolving into **autonomous agent ecosystems**.

Current approaches:
- REST APIs
- Webhooks
- Message brokers

create fragile, tightly coupled integrations.

ACP solves this by introducing:

- Identity-first communication
- Signed and encrypted message envelopes
- Transport independence (HTTP, AMQP, MQTT)
- Relay-based cross-network collaboration

---

# ACP Reference Implementation

This repository contains a first reference implementation of the Agent Communication Protocol (ACP):

- `sdks/python`: ACP Python SDK
- `sdks/java`: minimal Java ACP client for poker-agent interoperability
- `sdks/rust`: internal Rust ACP SDK
- `sdks/typescript`: internal TypeScript ACP SDK
- `sdks/go`: internal Go ACP SDK
- `sdks/mojo`: internal Mojo ACP SDK wrapper over ACP Python runtime
- `relay-dev`: minimal HTTP relay
- `tools/chess-player`: Vaadin chess player using ACP Java SDK for agent-to-agent play
- `tools/python-chess-player`: Chess player using ACP Python SDK for direct agent-to-agent play
- `examples`: runnable demos (one-to-one, one-to-many, `ACK`/`FAIL`, `COMPENSATE`, `CAPABILITIES`)

## Quickstart

## Quick Start

For a minimal local setup (install, identity, ping), see `getting-started/README.md`.

Install Python SDK:

```bash
pip install acp-sdk
pip install acp-cli
```
Build Rust SDK:

```bash
cargo check --manifest-path sdks/rust/Cargo.toml
```

Build TypeScript SDK:

```bash
cd acp-sdk-typescript
npm install
npm run lint
npm run test
```

Build Go SDK:

```bash
cd sdks/go
go test ./...
```

Run Mojo wrapper example (requires Mojo + ACP Python SDK environment):

```bash
cd acp-sdk-mojo
mojo examples/overlay_http_client.mojo
```

Start relay:

```bash
ACP_DISCOVERY_SCHEME=http uvicorn app:app --app-dir acp-relay --host 0.0.0.0 --port 8080
```

Start recipient agents:

```bash
python examples/run_agent_server.py --agent-id agent:shipping.bot@localhost:9001 --port 9001 --relay-url http://localhost:8080
python examples/run_agent_server.py --agent-id agent:finance.bot@localhost:9002 --port 9002 --relay-url http://localhost:8080
```

Run one-to-one message:

```bash
python examples/send_basic.py --relay-url http://localhost:8080 --recipient-id agent:shipping.bot@localhost:9001 --delivery-mode auto
```

Run one-to-many + compensation:

```bash
python examples/send_multi_recipient.py --relay-url http://localhost:8080 --delivery-mode auto
```

Run capabilities exchange:

```bash
python examples/capabilities_demo.py --relay-url http://localhost:8080
```

Overlay adapter demo (existing-style HTTP endpoint wrapped with ACP):

```bash
pip install fastapi uvicorn
python examples/overlay_http_service.py --allow-insecure-http --base-url http://localhost:9010
python examples/overlay_http_client.py --allow-insecure-http --target-base-url http://localhost:9010
```

Rust overlay outbound demo client against the same service:

```bash
ACP_TARGET_BASE_URL=http://localhost:9010 \
ACP_ALLOW_INSECURE_HTTP=true \
cargo run --manifest-path sdks/rust/Cargo.toml --example overlay_http_client
```

Flask wrapper variant:

```bash
pip install flask
python examples/overlay_flask_service.py --allow-insecure-http --base-url http://localhost:9020
python examples/overlay_http_client.py --allow-insecure-http --target-base-url http://localhost:9020
```

Spring-style wrapper template:

- `examples/java_overlay_spring/OverlayControllerExample.java`

## Notes

- Discovery order in SDK: cache -> `.well-known` -> relay hints (`/discover`) -> optional directories (`/discover`)
- Public scope in this repo: SDKs, CLI, and `relay-dev`; out-of-scope future ACP features are not included in this repository (see `DEVELOPMENT_BOUNDARY.md`).
- Delivery modes in SDK: `auto` (prefer direct endpoint, fallback relay), `direct`, `relay`
- Relay forwards encrypted ACP messages and never decrypts payloads
- Relay store-and-forward controls:
  - `ACP_RELAY_STORE_AND_FORWARD=true|false`
  - `ACP_RELAY_RETRY_INTERVAL_SECONDS=<float>`
  - `ACP_RELAY_MAX_RETRY_ATTEMPTS=<int>`
  - `ACP_RELAY_RETRY_BACKOFF_SECONDS=<float>`
- Relay retry inspection endpoints:
  - `GET /pending-deliveries`
  - `POST /pending-deliveries/process`
- Cryptography defaults:
  - Ed25519 signatures
  - X25519 key agreement
  - AES-256-GCM payload encryption
