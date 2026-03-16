# ACP Framework Overlay Wrapper Results

Date: 2026-03-15

## 1. Files Changed

Primary implementation:

- `acp-sdk-python/acp/overlay_framework.py`
- `acp-sdk-python/acp/__init__.py`
- `acp-sdk-python/tests/test_overlay_framework.py`
- `acp-sdk-java/src/main/java/org/acp/client/framework/OverlayHttpRuntime.java`
- `acp-sdk-java/src/test/java/org/acp/client/framework/OverlayHttpRuntimeTest.java`

Examples:

- `examples/overlay_http_service.py` (now uses framework wrapper runtime)
- `examples/overlay_flask_service.py` (new)
- `examples/overlay_http_client.py` (reused as outbound caller)
- `examples/java_overlay_spring/OverlayControllerExample.java` (new Spring-style template)
- `examples/java_overlay_spring/README.md` (new)

Docs:

- `README.md`
- `docs/28_acp_quick_start.md`
- `acp-sdk-java/README.md`
- `docs/25_acp_current_implementation_status.md`

## 2. Wrapper APIs Introduced

### Python

Module: `acp.overlay_framework`

- `OverlayFrameworkRuntime`
  - `handle_message_body(...)`
  - `well_known_document()`
  - `identity_document_payload()`
  - `send_business_payload(...)`
  - `send_acp(...)` (frozen convenience alias)
- `OverlayClient`
  - `send_acp(...)`
- `acp_overlay_inbound(config=...)` (thin decorator helper for payload-level wrapping)
- `OverlayHttpResponse`
- `register_fastapi_overlay_routes(...)`
- `register_flask_overlay_routes(...)`
- `OverlayFrameworkError`

Design notes:

- Wrapper reuses existing `OverlayInboundAdapter` and `OverlayOutboundAdapter`.
- Inbound handling keeps ACP verification/decrypt/signature logic in existing runtime.
- Well-known and identity endpoints are exposed via wrapper helpers.
- Well-known wrapper routes emit advisory cache headers (`Cache-Control: public, max-age=300`).

### Java

Package: `org.acp.client.framework`

- `OverlayHttpRuntime`
  - `handleMessageBody(...)`
  - `handle(...)`
  - static `handle(..., OverlayConfig)`
  - `wellKnownDocument()`
  - `wellKnownHeaders()`
  - `identityDocumentPayload()`
  - `sendBusinessPayload(...)`
  - `sendAcp(...)`
- `OverlayHttpRuntime.HttpOverlayResponse`

Design notes:

- Spring-friendly controller integration without introducing a Spring dependency inside SDK.
- Wrapper reuses existing `OverlayInboundAdapter` and `OverlayOutboundAdapter`.
- Includes frozen convenience aliases mirroring the wrapper quick-start surface.

## 3. Examples Added

Python:

- FastAPI wrapper example: `examples/overlay_http_service.py`
- Flask wrapper example: `examples/overlay_flask_service.py`
- Outbound sender example: `examples/overlay_http_client.py`

Java:

- Spring-style controller template: `examples/java_overlay_spring/OverlayControllerExample.java`

## 4. Tests Added / Updated

Python:

- `acp-sdk-python/tests/test_overlay_framework.py` (new)
  - runtime inbound + invalid payload behavior
  - outbound bootstrap via `/.well-known/acp`
  - FastAPI route registration (if framework test deps available)
  - Flask route registration (if Flask available)

Java:

- `acp-sdk-java/src/test/java/org/acp/client/framework/OverlayHttpRuntimeTest.java` (new)
  - inbound ACP handling + invalid payload behavior
  - outbound bootstrap via `/.well-known/acp`

## 5. Remaining Ergonomics Gaps

- No annotation-based framework autowiring package yet (intentional; current pass is thin wrapper first).
- FastAPI test-client path depends on optional `httpx`; test is skipped when unavailable.
- No dedicated Spring Boot starter or auto-configuration module yet.

## 6. Recommended Next Step

Build a small optional framework package layer (separate from core SDK) with:

- Spring Boot auto-configuration starter for `OverlayHttpRuntime`
- FastAPI/Flask mini-extension packages
- endpoint/path conventions and config binding helpers

while keeping ACP core/runtime semantics unchanged.
