# ACP Reference Implementation (Python)

This repository contains a first reference implementation of the Agent Communication Protocol (ACP):

- `acp-sdk-python`: ACP Python SDK
- `acp-relay`: minimal HTTP relay
- `examples`: runnable demos (one-to-one, one-to-many, `ACK`/`FAIL`, `COMPENSATE`, `CAPABILITIES`)
- `docs`: ACP protocol notes and design docs

## Quickstart

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./acp-sdk-python
pip install -e ./acp-relay
```

Start relay:

```bash
ACP_DISCOVERY_SCHEME=http uvicorn app:app --app-dir acp-relay --host 0.0.0.0 --port 8080
```

Start recipient agents:

```bash
python examples/run_agent_server.py --agent-id agent:shipping.bot@localhost:9001 --port 9001 --relay-url http://localhost:8080
python examples/run_agent_server.py --agent-id agent:finance.bot@localhost:9002 --port 9002 --relay-url http://localhost:8080
```

Run one-to-one message:

```bash
python examples/send_basic.py --relay-url http://localhost:8080 --recipient-id agent:shipping.bot@localhost:9001
```

Run one-to-many + compensation:

```bash
python examples/send_multi_recipient.py --relay-url http://localhost:8080
```

Run capabilities exchange:

```bash
python examples/capabilities_demo.py --relay-url http://localhost:8080
```

## Notes

- Discovery order in SDK: cache -> `.well-known` -> relay hints (`/discover`)
- Relay forwards encrypted ACP messages and never decrypts payloads
- Cryptography defaults:
  - Ed25519 signatures
  - X25519 key agreement
  - AES-256-GCM payload encryption
