# ACP Python Chess Player

This tool provides a Python/FastAPI ACP chess player with the same match orchestration and ACP endpoints as the Java chess player.

HTTPS hardening note:

- ACP now defaults to HTTPS-first behavior for HTTP-based paths.
- Local demo runs that use `http://` must set `CHESS_AGENT_ACP_ALLOW_INSECURE_HTTP=true` explicitly.

## Features

- ACP endpoints:
  - `POST /api/v1/acp/messages`
  - `GET /.well-known/acp`
  - `GET /api/v1/acp/identity`
- Chess APIs:
  - `POST /api/v1/chess/matches/start`
  - `GET /api/v1/chess/matches`
  - `GET /api/v1/chess/matches/{id}`
- Web UI:
  - `/`
  - `/chess`

## Local setup

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e acp-sdk-python
pip install -e tools/python-chess-player[dev]
```

Run tests:

```bash
pytest tools/python-chess-player/tests
```

## Run two players locally

Terminal 1 (white):

```bash
CHESS_AGENT_SERVER_PORT=8088 \
CHESS_AGENT_COLOR=WHITE \
CHESS_AGENT_LOCAL_AGENT_ID=agent:player1@localhost:8088 \
CHESS_AGENT_REMOTE_AGENT_ID=agent:player2@localhost:8089 \
CHESS_AGENT_PUBLIC_BASE_URL=http://localhost:8088 \
CHESS_AGENT_ACP_ALLOW_INSECURE_HTTP=true \
CHESS_AGENT_ACP_STORAGE_DIR=$PWD/.chess-agent/player1/acp \
CHESS_AGENT_PGN_EXPORT_DIR=$PWD/.chess-agent/player1/pgn \
CHESS_AGENT_STATE_FILE=$PWD/.chess-agent/player1/state/matches.json \
python -m app.main
```

Terminal 2 (black):

```bash
CHESS_AGENT_SERVER_PORT=8089 \
CHESS_AGENT_COLOR=BLACK \
CHESS_AGENT_LOCAL_AGENT_ID=agent:player2@localhost:8089 \
CHESS_AGENT_REMOTE_AGENT_ID=agent:player1@localhost:8088 \
CHESS_AGENT_PUBLIC_BASE_URL=http://localhost:8089 \
CHESS_AGENT_ACP_ALLOW_INSECURE_HTTP=true \
CHESS_AGENT_ACP_STORAGE_DIR=$PWD/.chess-agent/player2/acp \
CHESS_AGENT_PGN_EXPORT_DIR=$PWD/.chess-agent/player2/pgn \
CHESS_AGENT_STATE_FILE=$PWD/.chess-agent/player2/state/matches.json \
python -m app.main
```

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

UIs:

- `http://localhost:8088`
- `http://localhost:8089`

## Run with Docker

From repository root:

```bash
docker compose -f tools/python-chess-player/docker-compose.yml up --build
```

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

## Run via relay

From repository root:

```bash
docker compose -f tools/python-chess-player/docker-compose-relay.yaml up --build
```

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```
