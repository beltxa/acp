# Poker Demo (ACP Direct)

This module contains a minimal poker dealer + player setup migrated to ACP for inter-agent messaging.

## Components

- `dealer`: Vaadin web UI + game engine. Sends gameplay events over ACP.
- `player`: autonomous poker player service. Compose runs four player instances (`Player-1` to `Player-4`).
- `common`: shared protocol and model types.

## Transport

- Default transport mode is `ACP` for both dealer and players.
- Delivery mode is configured as `direct` by default.
- Discovery uses direct `/.well-known/acp` endpoints (`http` in local Docker).
- Relay is not required or used in the default configuration.

## Run with Docker

From repo root:

```bash
docker compose -f tools/poker-demo/docker-compose.yml up --build -d
```

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

Stop:

```bash
docker compose -f tools/poker-demo/docker-compose.yml down
```
