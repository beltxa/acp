# ACP Canonical Interoperability Demo

## Purpose

This is the canonical interoperability proof layer for ACP.

It exists to show protocol behavior across SDK boundaries with a smaller footprint than showcase applications.

## Layer Classification

- Layer: **Interoperability proof**
- Protocol source of truth: `sdks/tests/vectors/` (not this folder)
- Showcase applications: `tools/` (not this folder)

## Proof Targets

This demo is used to validate:

1. cross-language communication
2. protocol-level compatibility
3. direct mode
4. optional relay mode
5. ack/fail flow
6. capability invocation (scaffolded)

## Current Status

| Proof item | Status |
| --- | --- |
| direct cross-language send/receive | implemented |
| ack/fail visibility | implemented |
| relay-mode cross-language path | experimental |
| capability invocation across languages | scaffolded |
| mojo participation | bridge-based |

## Direct Mode (Minimal Flow)

### 1) Start Python overlay service (receiver)

From repository root:

```bash
python examples/overlay_http_service.py --allow-insecure-http --base-url http://localhost:9010
```

### 2) Run language clients against the same ACP target

TypeScript:

```bash
cd sdks/typescript
npm run build
node dist/examples/overlay_http_client.js
```

Rust:

```bash
cargo run --manifest-path sdks/rust/Cargo.toml --example overlay_http_client
```

Go:

```bash
go run ./sdks/go/examples/overlay_http_client
```

Mojo (bridge-based):

```bash
cd sdks/mojo
mojo examples/overlay_http_client.mojo
```

### 3) ACK/FAIL check

- ACK-like success path: run clients while receiver is available.
- FAIL path: stop receiver and rerun client to confirm delivery failure state is surfaced.

## Relay Mode (Experimental Scaffold)

Relay-mode canonicalization is tracked as experimental here:

- use `relay-dev/` for local relay runtime
- reuse the same sender/receiver scenario intent
- preserve the same outcome labeling in parity reporting

This remains intentionally smaller than showcase orchestration.

## Related Assets

- Parity model: `sdks/tests/PARITY_MODEL.md`
- Example taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility matrix: `sdks/tests/compatibility-matrix.md`
- Public-safe ecosystem overview: `sdks/tests/INTEROPERABILITY_LAYERS.md`
