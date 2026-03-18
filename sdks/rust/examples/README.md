# Rust Examples

## 1. What The Example Shows

Canonical Rust scenario coverage:

- `overlay_http_client`: implemented (`overlay_http_client.rs`)
- `hello_world`: not yet implemented
- `ping_demo`: not yet implemented
- `send_basic`: not yet implemented
- `send_multi_recipient`: not yet implemented
- `discover_well_known`: experimental (test-backed, no dedicated example file)

## 2. Prerequisites

- Rust stable toolchain

```bash
cargo test --manifest-path sdks/rust/Cargo.toml
```

## 3. How To Run

```bash
cargo run --manifest-path sdks/rust/Cargo.toml --example overlay_http_client
```

## 4. Expected Behavior

- The example resolves target well-known metadata before sending.
- Delivery outcomes are printed as formatted JSON.
- Behavior aligns with ACP overlay protocol semantics.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

