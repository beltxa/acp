# ACP Overlay Adapter Pass Results

Date: 2026-03-15

## Scope Completed

Implemented the first real HTTP overlay adapter path using existing ACP runtime logic.

Completed:

- inbound overlay handling
- outbound overlay send helper
- `/.well-known/acp` bootstrap integration
- HTTPS-first/insecure-override compatibility through existing runtime policies
- Python and Java adapter coverage
- demo/example visibility updates

## Adapter APIs Introduced

Python SDK:

- `acp.overlay.is_acp_http_message(...)`
- `acp.overlay.OverlayInboundAdapter`
- `acp.overlay.OverlayOutboundAdapter`
- `acp.overlay.OverlayTarget`
- `acp.overlay.OverlayAdapterError`

Java SDK:

- `org.acp.client.OverlayInboundAdapter`
- `org.acp.client.OverlayOutboundAdapter`
- `AcpAgent.resolveWellKnown(...)` helper exposure for adapter use

## Behavior Notes

- Inbound adapter uses existing ACP inbound logic (`handle_incoming` / `receive`) for verification, decryption, dedup, and ACK/FAIL handling.
- Inbound adapter now surfaces top-level `response_message` and `state` so handler responses can be returned directly by HTTP endpoints.
- Outbound adapter supports well-known bootstrap from a base URL, resolves identity metadata, and reuses existing send/delivery logic.

## Files Changed (Overlay Pass)

- `acp-sdk-python/acp/overlay.py`
- `acp-sdk-python/acp/__init__.py`
- `acp-sdk-java/src/main/java/org/acp/client/OverlayInboundAdapter.java`
- `acp-sdk-java/src/main/java/org/acp/client/OverlayOutboundAdapter.java`
- `acp-sdk-java/src/main/java/org/acp/client/AcpAgent.java`
- `examples/overlay_http_service.py`
- `examples/overlay_http_client.py`
- `README.md`
- `demo/README.md`
- `docs/28_acp_quick_start.md`
- `acp-sdk-java/README.md`
- `acp-sdk-python/acp_cli/README.md`

## Tests Added / Updated

Python:

- `acp-sdk-python/tests/test_overlay_adapter.py` (updated response-shape coverage)

Java:

- `acp-sdk-java/src/test/java/org/acp/client/OverlayAdapterTest.java` (new)

Overlay-adjacent well-known hardening used by adapters:

- `acp-sdk-python/tests/test_well_known_validation.py`
- `acp-sdk-java/src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java`
- `acp-relay/tests/test_well_known_resolver.py`

## Demo / Example Changes

- Added runnable overlay service example wrapping an existing-style `/orders` endpoint.
- Added outbound overlay client example using well-known bootstrap.
- Added quick-start/demo references so overlay mode is visible in normal demo usage docs.

## Remaining Overlay Gaps (Deferred)

- No framework-specific middleware packages (Flask/Spring bootstraps) yet.
- No non-HTTP overlay adapters.
- No relay-side overlay control-plane additions (intentionally out of scope).
