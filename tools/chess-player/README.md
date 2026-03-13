# ACP Chess Player

This tool is a Vaadin-based chess player that uses `acp-sdk-java` for direct agent-to-agent communication.

Two instances can play each other by configuring reciprocal ACP agent IDs and endpoints.

## Build

From repository root:

```bash
mvn -f acp-sdk-java/pom.xml -DskipTests install
mvn -f tools/chess-player/pom.xml test
```

## Run Locally (two terminals)

Terminal 1 (white):

```bash
CHESS_AGENT_SERVER_PORT=8088 \
CHESS_AGENT_COLOR=WHITE \
CHESS_AGENT_LOCAL_AGENT_ID=agent:player1@localhost:8088 \
CHESS_AGENT_REMOTE_AGENT_ID=agent:player2@localhost:8089 \
CHESS_AGENT_PUBLIC_BASE_URL=http://localhost:8088 \
mvn -f tools/chess-player/pom.xml spring-boot:run
```

Terminal 2 (black):

```bash
CHESS_AGENT_SERVER_PORT=8089 \
CHESS_AGENT_COLOR=BLACK \
CHESS_AGENT_LOCAL_AGENT_ID=agent:player2@localhost:8089 \
CHESS_AGENT_REMOTE_AGENT_ID=agent:player1@localhost:8088 \
CHESS_AGENT_PUBLIC_BASE_URL=http://localhost:8089 \
mvn -f tools/chess-player/pom.xml spring-boot:run
```

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

UI:
- `http://localhost:8088`
- `http://localhost:8089`

## Run With Docker

From repository root:

```bash
docker compose -f tools/chess-player/docker-compose.yml up --build
```

Start a game:

```bash
curl -X POST http://localhost:8088/api/v1/chess/matches/start
```

## ACP Endpoints

- `POST /api/v1/acp/messages`
- `GET /.well-known/acp/agents/{name}`
- `GET /api/v1/acp/identity`
