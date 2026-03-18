# Poker Demo — ACP Multi-Language Interoperability

> Showcase application layer: this demo proves ACP interoperability in a domain-rich game scenario.  
> It is **not** the protocol contract source and **not** the parity benchmark.

This demo shows a poker table coordinated through ACP, with independent agents implemented in different languages communicating through the same protocol semantics.

---

## What this demo proves

This demo is useful because poker naturally requires:

- multiple independent participants
- repeated turn-based coordination
- private and public state
- deterministic sequencing
- reliable dealer/player message exchange

ACP is the communication layer that makes those interactions work consistently across runtimes.

---

## Demo modes

### 1. Java baseline
A full Java deployment used as the reference implementation.

### 2. Polyglot deployment
A mixed-language deployment proving that ACP agents implemented in different runtimes can participate in the same game flow.

---

## Components

- `dealer`: poker table coordinator and web UI
- `common`: shared game and protocol model types
- `java-player`: Java ACP poker player
- `python-player`: Python ACP poker player
- `go-player`: Go ACP poker player
- `rust-player`: Rust ACP poker player
- `typescript-player`: TypeScript ACP poker player

---

## Interoperability claim

The polyglot deployment is the important one.

It demonstrates that:

- the same ACP message semantics work across languages
- players can participate without language-specific coupling
- the dealer can coordinate a table without caring which runtime each player uses

---

## Transport model

- transport protocol: ACP
- default delivery mode: `direct`
- discovery: `/.well-known/acp`
- relay: not required in the default local setup

This keeps the demo focused on protocol interoperability rather than infrastructure complexity.

---

## Run the Java baseline

From repo root:

```bash
docker compose -f tools/poker-demo/docker-compose.yml up --build -d
```

Deployment:

- `Dealer [Java]` -> `Entity-E`
- `Player 1 [Java]` -> `Entity-A`
- `Player 2 [Java]` -> `Entity-B`
- `Player 3 [Java]` -> `Entity-C`
- `Player 4 [Java]` -> `Entity-D`

---

## Run the polyglot interoperability demo

From repo root:

```bash
docker compose -f tools/poker-demo/docker-compose-polyglot.yml up --build -d
```

Deployment:

- `Player 1 [Go]` -> `Entity-A`
- `Player 2 [Python]` -> `Entity-B`
- `Player 3 [Rust]` -> `Entity-C`
- `Player 4 [TypeScript]` -> `Entity-D`
- `Dealer [Java]` -> `Entity-E`

---

## Start a game manually

Deploying either environment does **not** start gameplay automatically.

Start the game only when you are ready:

- Use the `Start Game` button in the dealer UI, or
- Call:

```bash
curl -u local-admin:poker-dealer-admin-pass -X POST http://localhost:8090/api/v1/dealer/start
```

---

## Access

Dealer UI:

- `http://localhost:8090`

Player service ports:

- `http://localhost:8091`
- `http://localhost:8092`
- `http://localhost:8093`
- `http://localhost:8094`

Default dealer credentials:

- username: `local-admin`
- password: `poker-dealer-admin-pass`

---

## Stop the demo

```bash
docker compose -f tools/poker-demo/docker-compose.yml down
docker compose -f tools/poker-demo/docker-compose-polyglot.yml down
```

---

## How to read this demo

Use the Java baseline to confirm expected gameplay behavior.

Use the polyglot deployment to verify that ACP is acting as a genuine protocol layer across:

- Java
- Python
- Go
- Rust
- TypeScript

That is the main value of this demo.
