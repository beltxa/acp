# ACP Getting Started

Fastest verified path: run a local `ping` in under 5 minutes.

## Prerequisites

- Python 3.11+ (or newer)
- `curl`
- macOS/Linux shell

## First success path (recommended)

From repository root:

```bash
./getting-started/quickstart_ping.sh
```

Expected output:

```text
Ping delivered successfully: ['DELIVERED']
# or ['ACKNOWLEDGED']
Quickstart completed in <seconds>s
```

The script:

1. creates a temporary virtual environment
2. installs `sdks/python` and `cli`
3. starts a local receiver agent
4. sends a direct `ping`
5. verifies terminal delivery state

If you want to reuse the virtual environment:

```bash
ACP_QUICKSTART_VENV=.venv-quickstart ./getting-started/quickstart_ping.sh
```

## Canonical single-file Hello World agent

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python
python examples/hello_world_agent.py
```

This creates/loads a local identity and publishes one capability (`ping`) in a minimal script.

## Manual flow (same ping steps, split)

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
