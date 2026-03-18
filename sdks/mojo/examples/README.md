# Mojo Examples

## 1. What The Example Shows

Canonical Mojo scenario coverage:

- `send_basic`: bridge-based (`send_basic.mojo`)
- `overlay_http_client`: bridge-based (`overlay_http_client.mojo`)
- `hello_world`: not yet implemented
- `ping_demo`: bridge-based (via Python runtime bridge)
- `send_multi_recipient`: not yet implemented
- `discover_well_known`: bridge-based (API surface available via bridge)

Mojo support in this repository is bridge-based and experimental.

## 2. Prerequisites

- Mojo toolchain available
- ACP Python runtime available in the same environment

Typical repo setup:

```bash
pip install -e sdks/python -e sdks/mojo
```

## 3. How To Run

From `sdks/mojo`:

```bash
mojo examples/send_basic.mojo
mojo examples/overlay_http_client.mojo
```

If your environment requires Python path wiring for the bridge, set `PYTHONPATH` accordingly.

## 4. Expected Behavior

- Example execution depends on bridge compatibility with the active Mojo/Python environment.
- Successful runs exercise ACP behavior through the Python runtime bridge.
- Status remains explicitly `bridge-based` in parity reporting.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

