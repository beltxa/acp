# Poker Rust Player

This service implements the ACP poker player runtime in Rust with the same ACP message flow as the Java player:

- receives ACP envelopes on `POST /api/v1/acp/messages`
- exposes `GET /.well-known/acp` and `GET /api/v1/acp/identity`
- handles poker events (`INVITATION`, `ACTION_REQUEST`, etc.) using the `UCW_POKER_V1` payload profile
- sends `JOIN_TABLE` and `ACTION_RESPONSE` messages back to the dealer via ACP

## Run locally

From repo root:

```bash
cd tools/poker-demo/rust-player
cargo run
```

## Key environment variables

- `SERVER_PORT` (default `8091`)
- `POKER_PLAYER_PLAYER_ID` (default `Player-1`)
- `POKER_PLAYER_LOCAL_AGENT_ID` (default `agent:player1@localhost:8091`)
- `POKER_PLAYER_DEALER_AGENT_ID` (default `agent:dealer@localhost:8090`)
- `POKER_PLAYER_PUBLIC_BASE_URL` (default `http://localhost:8091`)
- `POKER_PLAYER_ACP_STORAGE_DIR` (default `/var/lib/poker-player/acp`)
- `POKER_PLAYER_ACP_ALLOW_INSECURE_HTTP` (default `false`)
- `POKER_PLAYER_ACP_DELIVERY_MODE` (default `direct`)
- `OPENAI_API_KEY` (optional, enables OpenAI-based action decisions)
