# Go Examples

## 1. What The Example Shows

Canonical Go scenario coverage:

- `send_basic`: implemented (`send_basic/main.go`)
- `overlay_http_client`: implemented (`overlay_http_client/overlay_http_client.go`)
- `hello_world`: not yet implemented
- `ping_demo`: not yet implemented
- `send_multi_recipient`: not yet implemented
- `discover_well_known`: experimental (test-backed, no dedicated example file)

## 2. Prerequisites

- Go 1.23+

```bash
cd sdks/go
go test ./...
```

## 3. How To Run

```bash
cd sdks/go
go run ./examples/send_basic
go run ./examples/overlay_http_client
```

## 4. Expected Behavior

- `send_basic` sends one ACP message to one recipient using canonical basic send semantics.
- `overlay_http_client` bootstraps target metadata from `/.well-known/acp` and performs overlay send.
- Output/errors reflect protocol-level send outcomes.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

