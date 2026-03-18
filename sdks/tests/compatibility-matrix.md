# ACP Compatibility Matrix

This matrix is the public, evidence-oriented status view for cross-SDK parity.

Legend:
- `implemented`
- `experimental`
- `bridge-based`
- `not yet implemented`
- `internal-only` (excluded from public parity claims)

## Canonical Example Scenarios

| Scenario | python | typescript | java | rust | go | mojo |
| --- | --- | --- | --- | --- | --- | --- |
| hello_world | implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented |
| ping_demo | implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented | bridge-based |
| send_basic | implemented | not yet implemented | not yet implemented | not yet implemented | implemented | bridge-based |
| send_multi_recipient | implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented |
| overlay_http_client | implemented | implemented | experimental | implemented | implemented | bridge-based |
| discover_well_known | experimental | experimental | experimental | experimental | experimental | bridge-based |

## Contract Vector Conformance Scope

| Contract suite | python | typescript | java | rust | go | mojo |
| --- | --- | --- | --- | --- | --- | --- |
| AMQP vectors (`sdks/tests/vectors/amqp`) | implemented | implemented | implemented | implemented | implemented | not yet implemented |
| MQTT vectors (`sdks/tests/vectors/mqtt`) | implemented | implemented | implemented | implemented | implemented | not yet implemented |
| Well-known vectors (`sdks/tests/vectors/well_known`) | implemented | implemented | implemented | implemented | implemented | not yet implemented |
| Security vectors (`sdks/tests/vectors/security`) | internal-only | internal-only | internal-only | internal-only | internal-only | internal-only |

## Interoperability Proof Layer

| Proof scenario | python | typescript | java | rust | go | mojo |
| --- | --- | --- | --- | --- | --- | --- |
| Canonical interop demo direct mode (`demos/canonical_interop`) | implemented | implemented | experimental | implemented | implemented | bridge-based |
| Canonical interop demo relay mode (`demos/canonical_interop`) | experimental | experimental | experimental | experimental | experimental | bridge-based |

## Honesty Rules

- `experimental` means evidence exists but is not yet a stable parity baseline.
- `bridge-based` means runtime behavior depends on another SDK/runtime bridge.
- `internal-only` means excluded from public parity claims.

