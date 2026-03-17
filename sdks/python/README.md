# ACP Python SDK (`acp-runtime`)

Status: `Published`

Python reference SDK for ACP identity-first agent communication.

## Install

Published package:

```bash
pip install acp-runtime
```

From this repository:

```bash
pip install -e sdks/python
```

## Minimal demo

Canonical single-file Hello World:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python
python examples/hello_world_agent.py
```

Fast local ping flow:

```bash
./getting-started/quickstart_ping.sh
```

## SDK capabilities

- create/load agent identities
- sign and verify identity documents
- build and send ACP messages over direct or relay paths
- request and compare agent capabilities
- use HTTP, AMQP, and MQTT transports
