# ACP Public Interoperability Layers

This document explains how ACP parity and interoperability assets fit together in the public repository.

## 1) Contract Parity Layer (Protocol Truth)

Location:
- `sdks/tests/vectors/`

This is the authoritative protocol contract layer. Parity claims are grounded here, not in app demos.

## 2) Example Parity Layer (SDK-Facing)

Location:
- `sdks/<language>/examples/`

This layer provides language-facing scenarios mapped to one canonical taxonomy:
- `hello_world`
- `ping_demo`
- `send_basic`
- `send_multi_recipient`
- `overlay_http_client`
- `discover_well_known`

## 3) Interoperability Proof Layer

Location:
- `demos/canonical_interop/`

This is the canonical multi-language proof that ACP works as a protocol across runtime boundaries.

## 4) Showcase Application Layer

Locations:
- `tools/chess-player/`
- `tools/poker-demo/`
- other UI/domain-rich applications under `tools/`

These are showcase applications. They are valuable demonstrations, but they are not the protocol contract source of truth and not the baseline parity benchmark.

## Evidence-Backed Claim Rule

Public parity claims must align with:

- `sdks/tests/compatibility-matrix.md`
- `sdks/tests/conformance_report.json`
- `sdks/tests/conformance_report.md`

If evidence is incomplete, status must be labeled explicitly (`experimental`, `bridge-based`, `not yet implemented`).
