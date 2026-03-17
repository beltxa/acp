# ACP Mojo SDK (`acp-sdk-mojo`)

Temporary pip-packaged Mojo-facing ACP SDK wrapper.

This package provides Mojo-callable wrappers over the existing ACP Python SDK so Mojo
programs can use the same ACP runtime behavior and security defaults without duplicating
protocol logic.

Parity is achieved by delegation to Python ACP runtime capabilities:

- ACP message model, send/receive, `ACK`/`FAIL` terminal behavior
- identity creation and document verification
- discovery via cache, relay hints, and `/.well-known/acp`
- HTTPS-first + optional mTLS + key-provider policy handling
- AMQP/MQTT transport support where configured in Python runtime
- overlay inbound/outbound wrappers

## Requirements

- Mojo runtime with Python interop enabled
- ACP Python SDK importable in the current environment (`import acp`)

## Install (temporary)

```bash
pip install acp-sdk-mojo
```

From this repository:

```bash
pip install -e sdks/mojo
```

## Example

```mojo
from python import PythonObject
from acp_sdk_mojo import load_or_create_agent, send_basic

fn main() raises:
    var options = PythonObject(dict())
    options["allow_insecure_http"] = True
    options["discovery_scheme"] = "http"
    let agent = load_or_create_agent("agent:mojo.sender@localhost:9051", options)
    var payload = PythonObject(dict())
    payload["kind"] = "mojo-demo"
    _ = send_basic(agent, PythonObject(["agent:receiver@localhost:9052"]), payload, "ctx:demo")
```

## Notes

- This SDK intentionally keeps ACP protocol logic in one place (Python runtime) and exposes
  a thin Mojo wrapper API.
- No secrets are logged by wrapper code.
