# ACP John Demo Environment

This folder contains a minimal, repeatable setup for the John demo flow:

1. direct HTTP communication
2. relay-assisted communication (registration + discovery)
3. Ricardo endpoint migration to cloud without John reconfiguration

## Files

- `relay/relay.demo.yaml` relay settings reference
- `relay/.env.example` relay runtime environment template
- `identities/john/` pre-generated John identity storage
- `identities/ricardo/` pre-generated Ricardo identity storage
- `config/john.chess.yaml` John run profile (direct + relay stages)
- `config/ricardo.chess.yaml` Ricardo run profile (direct + relay + cloud update stages)
- `scripts/start_demo.sh` helper for relay lifecycle and agent runtime commands
- `scripts/prewarm_registry.sh` pre-warm relay registry and verify discovery

## John-side vs Ricardo-side assets

John side needs:

- `demo/config/john.chess.yaml`
- `demo/identities/john/`

Ricardo side needs:

- `demo/config/ricardo.chess.yaml`
- `demo/identities/ricardo/`
- relay access (`http://localhost:8080` for local demo)

## Prerequisites

- repo root is `/Users/rsanchez/work/acp`
- `.venv` with ACP Python SDK + relay deps (already used by demo scripts)
- free ports: `8080` (relay), `8088` (John), `8089` (Ricardo)

## One-time prep

From repo root:

```bash
./demo/scripts/start_demo.sh init-identities
```

This recreates demo identities and pre-seeds discovery caches for direct stage.

## Stage 1: Direct HTTP communication

Terminal 1 (John):

```bash
./demo/scripts/start_demo.sh run-john-direct
```

Terminal 2 (Ricardo):

```bash
./demo/scripts/start_demo.sh run-ricardo-direct
```

Terminal 3 (send test from John to Ricardo):

```bash
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main \
  --storage-dir demo/identities/john \
  message send \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo \
  --payload-json '{"stage":"direct","move":"e2e4"}' \
  --delivery-mode direct
```

## Stage 2: Relay-assisted communication

Start relay:

```bash
./demo/scripts/start_demo.sh relay-up
```

Pre-warm registry (register Ricardo and verify John discovery):

```bash
./demo/scripts/start_demo.sh prewarm
```

Run agents in relay mode:

```bash
./demo/scripts/start_demo.sh run-john-relay
```

```bash
./demo/scripts/start_demo.sh run-ricardo-relay
```

Test relay-assisted message:

```bash
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main \
  --storage-dir demo/identities/john \
  message send \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo \
  --payload-json '{"stage":"relay","move":"g1f3"}' \
  --delivery-mode relay \
  --relay http://localhost:8080
```

Inspect relay:

```bash
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main relay status --relay http://localhost:8080
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main relay registry list --relay http://localhost:8080
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main relay routes show --relay http://localhost:8080
```

## Stage 3: Ricardo cloud endpoint update path

Update Ricardo registration to cloud endpoint (example value):

```bash
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main \
  --storage-dir demo/identities/ricardo \
  register update \
  --agent-id agent:ricardo.chess@demo \
  --relay http://localhost:8080 \
  --endpoint https://ricardo-chess-demo.example.com/api/v1/acp/messages
```

Or via prewarm script:

```bash
CLOUD_ENDPOINT=https://ricardo-chess-demo.example.com/api/v1/acp/messages \
  ./demo/scripts/prewarm_registry.sh
```

John keeps the same config and still discovers `agent:ricardo.chess@demo` via relay.

If you run the update manually, refresh John's discovery cache before re-check:

```bash
rm -f demo/identities/john/discovery_cache.json
PYTHONWARNINGS=ignore::RuntimeWarning PYTHONPATH=acp-sdk-python .venv/bin/python -m acp_cli.main \
  --storage-dir demo/identities/john \
  --json \
  discover get \
  --agent-id agent:ricardo.chess@demo \
  --relay-hint http://localhost:8080 \
  --scheme http
```

## Stop relay

```bash
./demo/scripts/start_demo.sh relay-down
```
