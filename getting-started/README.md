# ACP Getting Started

This guide covers a minimal local developer workflow:

1. Install the Python SDK + CLI
2. Create an identity
3. Send a local `ping` message

## Prerequisites

- Python 3.11+
- macOS/Linux shell

## 1. Install from this repository

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python
pip install fastapi uvicorn
```

## 2. Create a local identity

```bash
acp --storage-dir /tmp/acp-gs --allow-insecure-http identity create \
  --agent-id agent:sender.bot@localhost:9010 \
  --direct-endpoint http://localhost:9010/acp/inbox

acp --storage-dir /tmp/acp-gs --allow-insecure-http identity show \
  --agent-id agent:sender.bot@localhost:9010
```

## 3. Send a local ping (direct delivery)

Create a local CLI config that enables HTTP discovery for localhost:

```bash
cat > /tmp/acp-gs-config.json <<'EOF'
{
  "storage_dir": "/tmp/acp-gs",
  "discovery_scheme": "http",
  "allow_insecure_http": true
}
EOF
```

Start a recipient agent server in terminal A:

```bash
python examples/run_agent_server.py \
  --agent-id agent:receiver.bot@localhost:9011 \
  --port 9011 \
  --public-host localhost \
  --relay-url http://localhost:8080 \
  --storage-dir /tmp/acp-gs \
  --allow-insecure-http
```

Send `ping` from terminal B:

```bash
acp --config /tmp/acp-gs-config.json \
  --storage-dir /tmp/acp-gs \
  --allow-insecure-http \
  message send \
  --from agent:sender.bot@localhost:9010 \
  --to agent:receiver.bot@localhost:9011 \
  --payload-json '{"type":"ping"}' \
  --delivery-mode direct \
  --context getting-started-ping
```

Expected output includes:

- `Message send result`
- `Success outcomes: 1/1`

## Cleanup

```bash
rm -rf /tmp/acp-gs /tmp/acp-gs-config.json
```

Note: this guide intentionally allows insecure HTTP for local development only.
