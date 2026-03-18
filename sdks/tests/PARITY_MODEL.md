# ACP Parity Model

## Purpose

This document defines how ACP parity, conformance, and interoperability claims are governed in the public repository.

Parity claims must be evidence-backed and protocol-first. If evidence is incomplete, status must be explicit.

## The 4-Layer Model

### 1. Contract Parity Layer (Protocol Truth)

Authoritative source:
- `sdks/tests/vectors/`
- `sdks/tests/vectors/manifest.yaml`

This layer defines protocol behavior independent of language runtime.

Use this layer for:
- message carriage semantics
- transport fixture expectations
- well-known document validation
- conformance expectations that are language-neutral

Do not use this layer for:
- UI behavior
- product packaging claims
- private governance/policy details

### 2. Example Parity Layer (Language-Facing Scenarios)

Primary location:
- `sdks/<language>/examples/`

This layer maps each SDK to a canonical scenario taxonomy so users can compare behavior by scenario intent, not syntax.

Parity in this layer is tracked with explicit labels:
- `implemented`
- `experimental`
- `bridge-based`
- `not yet implemented`

### 3. Interoperability Proof Layer (Canonical Multi-Language Demo)

Primary location:
- `demos/canonical_interop/`

This layer provides one small, protocol-first cross-language proof. It is intentionally smaller than showcase applications and is used for interoperability evidence.

### 4. Showcase Application Layer

Primary locations:
- `tools/`
- chess and poker application trees

This layer demonstrates domain-rich usage. It is not protocol truth, not example parity baseline, and not conformance evidence.

## Evidence Rules

1. Protocol parity claims must reference contract vectors and/or conformance outputs.
2. Example parity claims must include per-SDK status labels.
3. Interoperability claims must point to canonical demo evidence, not showcase apps.
4. Unknown or incomplete coverage must be labeled explicitly.

## Public-Safety and Boundary Rules

- Prefer protocol truth over demo richness.
- Prefer smaller canonical proof over complex showcase orchestration.
- Keep private enterprise/premium roadmap details out of public parity framing.
- Keep `demos/` as interoperability proof and `tools/` as showcase applications.
- Do not promote relay-dev behavior into enterprise behavior.

## Release Gate Reference

The minimum release parity gate is defined in:
- `sdks/tests/RELEASE_PARITY_GATE.md`

