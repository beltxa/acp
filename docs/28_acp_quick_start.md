# ACP Quick Start Guide

## Purpose

This guide provides the correct commands to start and run the current chess and poker demos in this repository.

It covers:

- chess demo in direct mode
- chess demo via relay
- poker demo in direct mode
- poker demo via relay

Security note:

- this quick start is intentionally local/demo-oriented and uses `http://localhost` endpoints
- for production-style deployments, use HTTPS endpoints and certificates by default
- optional enterprise profile: enable HTTP mTLS (`mtls_enabled`, `ca_file`, `cert_file`, `key_file`) for mutual TLS authentication

Run all commands from repository root (`/Users/rsanchez/work/acp`).

---

## Prerequisites

- Docker Desktop (or Docker Engine with Compose v2)
- Ports available: `8080`, `8088`, `8089`, `8090`, `8091`, `8092`, `8093`, `8094`
- Optional: `OPENAI_API_KEY` for stronger poker player decisions

---

## Repo Paths Used

```
tools/chess-player/docker-compose.yml
tools/chess-player/docker-compose-relay.yaml
tools/poker-demo/docker-compose.yml
tools/poker-demo/docker-compose-relay.yaml
```

---

## 1. Chess Demo (Direct)

Start:

```bash
docker compose -f tools/chess-player/docker-compose.yml up --build -d
```

Demo-only transport note: local UI and direct ACP endpoints use HTTP for local convenience.

Open UIs:

- `http://localhost:8088`
- `http://localhost:8089`

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

Follow logs:

```bash
docker compose -f tools/chess-player/docker-compose.yml logs -f
```

Stop:

```bash
docker compose -f tools/chess-player/docker-compose.yml down
```

---

## 2. Chess Demo (Relay)

Start:

```bash
docker compose -f tools/chess-player/docker-compose-relay.yaml up --build -d
```

Notes:

- This stack includes relay + two players + `relay-bootstrap` registration job.
- Players communicate with `CHESS_AGENT_ACP_DELIVERY_MODE=relay`.
- Relay/UI endpoints shown here are local HTTP demo endpoints.

Open UIs:

- `http://localhost:8088`
- `http://localhost:8089`

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

Follow logs:

```bash
docker compose -f tools/chess-player/docker-compose-relay.yaml logs -f
```

Stop:

```bash
docker compose -f tools/chess-player/docker-compose-relay.yaml down
```

---

## 3. Poker Demo (Direct)

Start:

```bash
docker compose -f tools/poker-demo/docker-compose.yml up --build -d
```

Demo-only transport note: local UI and ACP endpoints use HTTP for local convenience.

Dealer UI:

- `http://localhost:8090`

Login:

- username: `local-admin`
- password: `poker-dealer-admin-pass`

Run the demo:

1. Sign in to dealer UI.
2. Click `Start Game`.
3. Observe player actions and table updates in the UI.

Player service endpoints:

- `http://localhost:8091`
- `http://localhost:8092`
- `http://localhost:8093`
- `http://localhost:8094`

Follow logs:

```bash
docker compose -f tools/poker-demo/docker-compose.yml logs -f
```

Stop:

```bash
docker compose -f tools/poker-demo/docker-compose.yml down
```

---

## 4. Poker Demo (Relay)

Start:

```bash
docker compose -f tools/poker-demo/docker-compose-relay.yaml up --build -d
```

Notes:

- This stack includes relay + dealer + 4 players + `relay-bootstrap` registration job.
- Dealer and players run with `ACP` transport and `relay` delivery mode.
- Relay/UI endpoints shown here are local HTTP demo endpoints.

Dealer UI:

- `http://localhost:8090`

Login:

- username: `local-admin`
- password: `poker-dealer-admin-pass`

Run the demo:

1. Sign in to dealer UI.
2. Click `Start Game`.

Follow logs:

```bash
docker compose -f tools/poker-demo/docker-compose-relay.yaml logs -f
```

Stop:

```bash
docker compose -f tools/poker-demo/docker-compose-relay.yaml down
```

---

## Troubleshooting

- If ports are already in use, stop existing stacks before starting a new one.
- Do not run direct and relay variants of the same demo at the same time (port conflicts).
- If you move beyond local/demo usage, switch endpoint configuration to HTTPS.
- For enterprise hardening, keep TLS verification enabled and add mTLS certificate material instead of insecure overrides.
