# ACP Getting Started

Minimal verified flow: install SDK + CLI from this repo and deliver a local `ping` in one command.

## Prerequisites

- Python 3.11+ (or newer)
- `curl`
- macOS/Linux shell

## Fast path (<5 minutes)

From repository root:

```bash
./getting-started/quickstart_ping.sh
```

What it does:

1. Creates a temporary virtual environment
2. Installs `sdks/python` and `cli` with `pip`
3. Starts a local receiver agent
4. Sends a direct `ping` from a local sender identity
5. Verifies delivery outcome is `DELIVERED` or `ACKNOWLEDGED`

If you want to keep the virtual environment for reuse:

```bash
ACP_QUICKSTART_VENV=.venv-quickstart ./getting-started/quickstart_ping.sh
```

## Manual flow (same steps, split)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python -e cli fastapi uvicorn

acp --storage-dir /tmp/acp-gs --allow-insecure-http identity create \
  --agent-id agent:sender.bot@localhost:9010 \
  --direct-endpoint http://localhost:9010/acp/inbox

python examples/run_agent_server.py \
  --agent-id agent:receiver.bot@localhost:9011 \
  --port 9011 \
  --public-host localhost \
  --relay-url http://localhost:8080 \
  --storage-dir /tmp/acp-gs \
  --allow-insecure-http
```

In another terminal:

```bash
acp --storage-dir /tmp/acp-gs --allow-insecure-http \
  message send \
  --from agent:sender.bot@localhost:9010 \
  --to agent:receiver.bot@localhost:9011 \
  --payload-json '{"type":"ping"}' \
  --delivery-mode direct \
  --context getting-started-ping
```

Note: this guide intentionally uses insecure HTTP for local development only.
