# ACP Canonical Example Taxonomy

## Canonical Scenario Set

The public cross-SDK scenario taxonomy is:

1. `hello_world`
2. `ping_demo`
3. `send_basic`
4. `send_multi_recipient`
5. `overlay_http_client`
6. `discover_well_known`

## Status Labels

- `implemented`: runnable scenario exists in the SDK example layer.
- `experimental`: scenario exists but is not yet a stable parity baseline.
- `bridge-based`: scenario depends on another SDK/runtime bridge.
- `not yet implemented`: no SDK example exists for that canonical scenario.

## Scenario Intent

| Scenario | Intent |
| --- | --- |
| `hello_world` | Minimal agent bootstrap and identity/well-known visibility. |
| `ping_demo` | End-to-end ping/ack flow proving basic protocol send/receive semantics. |
| `send_basic` | Single-recipient SEND message with simple payload. |
| `send_multi_recipient` | Same message intent delivered to multiple recipients. |
| `overlay_http_client` | Overlay-style bootstrap via `/.well-known/acp` and protocol send through a target base URL. |
| `discover_well_known` | Resolve and validate well-known metadata for a remote agent/base URL. |

## Current Mapping by SDK

| Scenario | Python | TypeScript | Java | Rust | Go | Mojo |
| --- | --- | --- | --- | --- | --- | --- |
| `hello_world` | implemented (`examples/hello_world_agent.py`) | not yet implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented |
| `ping_demo` | implemented (`getting-started/quickstart_ping.sh` + Python runtime) | not yet implemented | not yet implemented | not yet implemented | not yet implemented | bridge-based (`getting-started` through Python runtime) |
| `send_basic` | implemented (`examples/send_basic.py`) | not yet implemented | not yet implemented | not yet implemented | implemented (`sdks/go/examples/send_basic/main.go`) | bridge-based (`sdks/mojo/examples/send_basic.mojo`) |
| `send_multi_recipient` | implemented (`examples/send_multi_recipient.py`) | not yet implemented | not yet implemented | not yet implemented | not yet implemented | not yet implemented |
| `overlay_http_client` | implemented (`examples/overlay_http_client.py`) | implemented (`sdks/typescript/examples/overlay_http_client.ts`) | experimental (`examples/java_overlay_spring/`) | implemented (`sdks/rust/examples/overlay_http_client.rs`) | implemented (`sdks/go/examples/overlay_http_client/overlay_http_client.go`) | bridge-based (`sdks/mojo/examples/overlay_http_client.mojo`) |
| `discover_well_known` | experimental (test-backed, no dedicated SDK example file) | experimental (test-backed, no dedicated SDK example file) | experimental (test-backed, no dedicated SDK example file) | experimental (test-backed, no dedicated SDK example file) | experimental (test-backed, no dedicated SDK example file) | bridge-based (API surface available through Python bridge) |

## Notes

- This taxonomy is scenario-intent parity, not syntax parity.
- `sdks/python/examples/` and `sdks/java/examples/` are currently documentation-mapped to existing repo examples/tests while dedicated SDK example files are expanded incrementally.
- Any scenario not marked `implemented` must not be counted as parity-complete.

