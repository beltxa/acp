# Mojo Conformance Runner Scaffold

## Purpose

This directory is reserved for Mojo conformance runner work aligned to:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Execute contract vectors through Mojo-facing ACP bridge paths.
2. Mark bridge-dependent outcomes explicitly as `bridge-based`.
3. Export result summaries for repository conformance reports.

## Current Status

`bridge-based (scaffold only)` — conformance location is established; runnable vector harness is not yet implemented.

## Planned Invocation

```bash
cd sdks/mojo
mojo tests/conformance/<runner>.mojo
```

