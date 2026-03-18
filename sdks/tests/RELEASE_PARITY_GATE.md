# ACP Release Parity Gate

Public parity claims are allowed only when all gate checks below are satisfied.

## Minimum Gate

1. Contract vector scope is defined and classified:
   - `sdks/tests/vectors/SCOPE.md`
   - `sdks/tests/vectors/manifest.yaml`
2. Canonical example taxonomy exists and SDK status labels are current:
   - `sdks/tests/EXAMPLE_TAXONOMY.md`
3. Compatibility matrix is current:
   - `sdks/tests/compatibility-matrix.md`
4. Canonical interoperability proof exists (implemented or explicitly scaffolded):
   - `demos/canonical_interop/`
5. Conformance report artifacts exist and are updated for the release:
   - `sdks/tests/conformance_report.json`
   - `sdks/tests/conformance_report.md`
6. Public/private boundary rules are preserved:
   - no enterprise/private roadmap leakage added
   - no showcase app reclassified as protocol contract truth

## Claim Language Policy

- Use `implemented` only with direct evidence.
- Use `experimental` if behavior exists but parity maturity is incomplete.
- Use `bridge-based` for bridge-dependent runtime paths.
- Use `not yet implemented` when no SDK example/conformance evidence exists.

## Required Review Before Tagging a Public Release

- README-level parity/status wording checked for consistency.
- Canonical demo status checked (direct and relay rows).
- Any `internal-only` vectors excluded from public parity claims.

