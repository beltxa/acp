# Python Conformance Runner Scaffold

## Purpose

This directory is reserved for Python conformance runners that execute authoritative contract vectors from:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Load vector manifest entries with `status: authoritative-public`.
2. Execute fixture validation against Python ACP runtime behavior.
3. Emit machine-readable results for aggregation into `sdks/tests/conformance_report.json`.

## Current Status

`implemented (scaffold only)` — structure is present, execution harness to be added incrementally.

## Planned Invocation

```bash
pytest sdks/python/tests/conformance
```

