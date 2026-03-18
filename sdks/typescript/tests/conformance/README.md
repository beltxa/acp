# TypeScript Conformance Runner Scaffold

## Purpose

This directory is reserved for TypeScript conformance runners that consume:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Select authoritative public vector entries.
2. Execute fixture checks against TypeScript ACP runtime behavior.
3. Emit structured run results for report aggregation.

## Current Status

`implemented (scaffold only)` — structure exists; full runner scripts are pending.

## Planned Invocation

```bash
cd sdks/typescript
npm test
```

