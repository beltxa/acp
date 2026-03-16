# ACP Reference Implementation

This repository contains a first reference implementation of the Agent Communication Protocol (ACP):

- `acp-sdk-python`: ACP Python SDK
- `acp-relay`: minimal HTTP relay
- `acp-sdk-java`: minimal Java ACP client for poker-agent interoperability
- `acp-sdk-rust`: internal Rust ACP SDK
- `tools/chess-player`: Vaadin chess player using ACP Java SDK for direct agent-to-agent play
- `examples`: runnable demos (one-to-one, one-to-many, `ACK`/`FAIL`, `COMPENSATE`, `CAPABILITIES`)
- `docs`: ACP protocol notes and design docs

## Quickstart

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./acp-sdk-python
pip install -e ./acp-relay
```

Build Rust SDK:

```bash
cargo check --manifest-path acp-sdk-rust/Cargo.toml
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
cargo run --manifest-path acp-sdk-rust/Cargo.toml --example overlay_http_client
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

- Discovery order in SDK: cache -> `.well-known` -> relay hints (`/discover`) -> optional enterprise directories (`/discover`)
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
