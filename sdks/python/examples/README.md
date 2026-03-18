# Python Examples

## 1. What The Example Shows

Canonical Python scenario coverage in this repository:

- `hello_world`: implemented
- `ping_demo`: implemented
- `send_basic`: implemented
- `send_multi_recipient`: implemented
- `overlay_http_client`: implemented
- `discover_well_known`: experimental (test-backed, no dedicated example file)

Current runnable files are in the repo-level `examples/` directory for historical compatibility.

## 2. Prerequisites

- Python 3.11+
- ACP Python SDK installed from repo:

```bash
pip install -e sdks/python
```

## 3. How To Run

From repository root:

```bash
python examples/hello_world_agent.py
python examples/send_basic.py
python examples/send_multi_recipient.py
python examples/overlay_http_client.py
./getting-started/quickstart_ping.sh
```

## 4. Expected Behavior

- Agent identity is created or loaded from storage.
- Messages are sent using ACP envelope semantics.
- `quickstart_ping.sh` demonstrates end-to-end ping flow.
- Overlay client path resolves `/.well-known/acp` before sending.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

