# ACP Demo Environments

Primary canonical interoperability proof:

- `demos/canonical_interop/`

This README documents an **extended John/Ricardo walkthrough** that is larger than the canonical proof and useful for richer staging.

Layering model:

- protocol contract truth: `sdks/tests/vectors/`
- canonical interoperability proof: `demos/canonical_interop/`
- extended demo environment: this file
- showcase applications: `tools/` (including chess/poker apps)

---

## What this demo demonstrates

This demo walks through three stages:

### 1. Direct communication
Two agents communicate directly over HTTP.

John Agent  →  Ricardo Agent

No relay. No shared infrastructure. Just protocol.

---

### 2. Relay-assisted communication

Agents communicate through a relay when direct connectivity is not available.

John Agent  →  Relay  →  Ricardo Agent

The protocol remains the same — only routing changes.

---

### 3. Endpoint migration without reconfiguration

Ricardo moves to a new (cloud) endpoint.

John does not change configuration.

John → Relay → Ricardo (new location)

Discovery + identity keep communication working.

---

## Why this matters

Traditional approaches require:

- endpoint reconfiguration
- tightly coupled integrations
- fragile assumptions about network topology

ACP introduces:

- identity-based addressing
- discovery-driven communication
- transport-independent routing

---

## Prerequisites

- run commands from repository root
- `.venv` with ACP Python SDK + relay dependencies
- free ports:
  - 8080 (relay)
  - 8088 (John)
  - 8089 (Ricardo)

---

## One-time setup

```bash
./demos/scripts/start_demo.sh init-identities
```

---

## Stage 1 — Direct communication

Start both agents:

```bash
./demos/scripts/start_demo.sh run-john-direct
```

```bash
./demos/scripts/start_demo.sh run-ricardo-direct
```

Send a message:

```bash
acp   --allow-insecure-http   --storage-dir demos/identities/john   message send   --from agent:john.chess@demo   --to agent:ricardo.chess@demo   --payload-json '{"stage":"direct","move":"e2e4"}'   --delivery-mode direct
```

---

## Stage 2 — Relay-assisted communication

Start relay:

```bash
./demos/scripts/start_demo.sh relay-up
```

Register and verify discovery:

```bash
./demos/scripts/start_demo.sh prewarm
```

Run agents:

```bash
./demos/scripts/start_demo.sh run-john-relay
```

```bash
./demos/scripts/start_demo.sh run-ricardo-relay
```

Send via relay:

```bash
acp   --allow-insecure-http   --storage-dir demos/identities/john   message send   --from agent:john.chess@demo   --to agent:ricardo.chess@demo   --payload-json '{"stage":"relay","move":"g1f3"}'   --delivery-mode relay   --relay http://localhost:8080
```

---

## Stage 3 — Endpoint migration

Update Ricardo to a new endpoint:

```bash
acp   --allow-insecure-http   --storage-dir demos/identities/ricardo   register update   --agent-id agent:ricardo.chess@demo   --relay http://localhost:8080   --endpoint https://ricardo-chess-demo.example.com/api/v1/acp/messages
```

John continues to send messages without changes.

---

## Inspect relay (optional)

```bash
acp --allow-insecure-http relay status --relay http://localhost:8080
acp --allow-insecure-http relay registry list --relay http://localhost:8080
acp --allow-insecure-http relay routes show --relay http://localhost:8080
```

---

## Overlay example (optional)

ACP can be layered on top of existing HTTP endpoints:

```bash
python examples/overlay_http_service.py --allow-insecure-http --base-url http://localhost:9010
python examples/overlay_http_client.py --allow-insecure-http --target-base-url http://localhost:9010
```

This uses `/.well-known/acp` discovery and ACP runtime verification without requiring a full rewrite.

---

## Important note

This demo uses local `http://` endpoints for simplicity.

In production:

- HTTPS is required
- optional mTLS and key management profiles can be used

---

## Summary

This demo shows that:

- agents communicate using identity, not endpoints
- routing can change without breaking communication
- multiple delivery modes share the same protocol
- ACP enables stable, loosely coupled agent systems
