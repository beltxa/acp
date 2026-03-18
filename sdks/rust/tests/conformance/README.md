# Rust Conformance Runner Scaffold

## Purpose

This directory is reserved for Rust conformance runners that validate ACP behavior against:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Read authoritative public vectors.
2. Execute fixture conformance checks in Rust tests.
3. Export structured status for repository conformance reports.

## Current Status

`implemented (scaffold only)` — path is established; full runner orchestration remains incremental.

## Planned Invocation

```bash
cargo test --manifest-path sdks/rust/Cargo.toml
```

