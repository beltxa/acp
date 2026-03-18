# Go Conformance Runner Scaffold

## Purpose

This directory is reserved for Go conformance runners driven by:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Load authoritative public vectors from the manifest.
2. Execute fixture checks through Go test entry points.
3. Produce machine-readable outcome summaries for global reporting.

## Current Status

`implemented (scaffold only)` — location is established; full runner implementation is pending.

## Planned Invocation

```bash
go test ./...
```

