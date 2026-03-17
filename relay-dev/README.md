# ACP Relay Dev (`acp-relay`)

Status: `Available from repo`

Development relay for local/test ACP routing.

## Run locally

```bash
ACP_DISCOVERY_SCHEME=http uvicorn app:app --app-dir relay-dev --host 0.0.0.0 --port 8080
```

## First-run reference

Use the verified ping flow:

```bash
./getting-started/quickstart_ping.sh
```

This package is intentionally development-scoped.
