# ACP CLI (`acp`)

Status: `Published`

Command-line interface for ACP identity management, discovery, and message delivery.

## Install

Published packages:

```bash
pip install acp-runtime acpctl
```

From this repository:

```bash
pip install -e sdks/python -e cli
```

Check installation:

```bash
acp --help
```

## First run

Use the repository quickstart ping flow:

```bash
./getting-started/quickstart_ping.sh
```

Details: `getting-started/README.md`.

## Common commands

```bash
acp identity create --agent-id agent:demo.bot@localhost:9010 --direct-endpoint http://localhost:9010/acp/inbox
acp message send --from agent:demo.bot@localhost:9010 --to agent:peer.bot@localhost:9011 --payload-json '{"type":"ping"}' --delivery-mode direct --allow-insecure-http
acp message capabilities --from agent:demo.bot@localhost:9010 --to agent:peer.bot@localhost:9011 --allow-insecure-http
```
