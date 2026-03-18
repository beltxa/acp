# TypeScript Examples

## 1. What The Example Shows

Canonical TypeScript scenario coverage:

- `overlay_http_client`: implemented
- `hello_world`: not yet implemented
- `ping_demo`: not yet implemented
- `send_basic`: not yet implemented
- `send_multi_recipient`: not yet implemented
- `discover_well_known`: experimental (test-backed, no dedicated example file)

## 2. Prerequisites

- Node.js 20+
- TypeScript SDK dependencies:

```bash
cd sdks/typescript
npm install
npm run build
```

## 3. How To Run

```bash
cd sdks/typescript
node dist/examples/overlay_http_client.js
```

or with `ts-node`/runtime tooling equivalent for `examples/overlay_http_client.ts`.

## 4. Expected Behavior

- The client bootstraps target identity from `/.well-known/acp`.
- A protocol SEND flow is executed via overlay adapter semantics.
- Output includes delivery outcomes and resolved target metadata.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

