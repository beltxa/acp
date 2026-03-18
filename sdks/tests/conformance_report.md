# ACP Conformance Report

Date: 2026-03-18  
Report mode: Initial scaffold

## Scope

Authoritative public contract vectors:
- `sdks/tests/vectors/amqp`
- `sdks/tests/vectors/mqtt`
- `sdks/tests/vectors/well_known`

Internal-only vectors (excluded from public parity claims):
- `sdks/tests/vectors/security`

## Current Conformance Summary

| SDK | AMQP vectors | MQTT vectors | Well-known vectors | Security vectors |
| --- | --- | --- | --- | --- |
| Python | implemented | implemented | implemented | internal-only |
| TypeScript | implemented | implemented | implemented | internal-only |
| Java | implemented | implemented | implemented | internal-only |
| Rust | implemented | implemented | implemented | internal-only |
| Go | implemented | implemented | implemented | internal-only |
| Mojo | not yet implemented | not yet implemented | not yet implemented | internal-only |

## Evidence Sources

- `sdks/tests/vectors/manifest.yaml`
- `sdks/tests/compatibility-matrix.md`
- `sdks/tests/vectors/amqp/conformance_report.md`

## Generation Plan

This report is currently maintained as a scaffold with evidence-backed status values from existing SDK test suites.

Planned automation flow:
1. Each SDK conformance runner emits machine-readable scenario results.
2. Results are merged into `sdks/tests/conformance_report.json`.
3. This markdown report is regenerated from the JSON artifact.

Until full automation is complete, status changes must include explicit evidence references in PR notes.

