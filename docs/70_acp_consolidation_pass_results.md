# ACP Consolidation / Adoption Pass Results

Date: 2026-03-15

## Step 1 — Well-Known Freeze

Completed:

- froze the `/.well-known/acp` model and validation behavior
- added malformed fixture vectors for required-field, type, URL, version, profile, and JSON-shape failures
- enforced explicit `identity_document` URL-reference-only decision (no embedded object)
- aligned Python SDK, Java SDK, and relay resolver validation with frozen model

Result artifact:

- `docs/67_acp_well_known_freeze_note.md`

## Step 2 — Overlay Adapter Pass

Completed:

- implemented thin inbound/outbound overlay adapters in Python and Java
- wired outbound overlay bootstrap through `/.well-known/acp` resolution
- hardened inbound adapter output for direct HTTP response usage (`response_message`, `state`)
- added runnable overlay examples for existing-style HTTP service adoption
- updated quick-start/demo/readme references to make overlay path visible

Result artifact:

- `docs/68_acp_overlay_adapter_results.md`

## Step 3 — Enterprise Consolidation Freeze

Completed:

- froze canonical enterprise security/provider config fields
- confirmed Python/Java/relay alignment for HTTPS-first + optional mTLS + local/vault key-provider model
- aligned Java default normalization for provider fields to match profile expectations
- froze enterprise example config set

Result artifact:

- `docs/69_acp_enterprise_consolidation_freeze_note.md`

## Key Design Decisions

- `identity_document` in well-known is now URL-reference-only.
- Well-known remains advisory; identity-document signature verification remains authoritative.
- Overlay adapters are thin wrappers over existing ACP runtime logic, not a parallel protocol stack.
- Enterprise config field set is frozen for Python/Java parity in current scope.

## High-Signal Files Changed

- `acp-sdk-python/acp/well_known.py`
- `acp-sdk-python/acp/discovery.py`
- `acp-sdk-python/acp/overlay.py`
- `acp-sdk-python/tests/test_well_known_validation.py`
- `acp-sdk-python/tests/test_overlay_adapter.py`
- `acp-relay/routing.py`
- `acp-relay/tests/test_well_known_resolver.py`
- `acp-sdk-java/src/main/java/org/acp/client/DiscoveryClient.java`
- `acp-sdk-java/src/main/java/org/acp/client/OverlayInboundAdapter.java`
- `acp-sdk-java/src/main/java/org/acp/client/OverlayOutboundAdapter.java`
- `acp-sdk-java/src/main/java/org/acp/client/AcpAgentOptions.java`
- `acp-sdk-java/src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java`
- `acp-sdk-java/src/test/java/org/acp/client/OverlayAdapterTest.java`
- `acp-sdk-java/src/test/java/org/acp/client/EnterpriseProfileConfigCompatibilityTest.java`
- `examples/overlay_http_service.py`
- `examples/overlay_http_client.py`
- `tests/vectors/well_known/*`

## Tests Added / Updated

Added:

- `acp-sdk-java/src/test/java/org/acp/client/OverlayAdapterTest.java`

Updated:

- `acp-sdk-python/tests/test_well_known_validation.py`
- `acp-sdk-python/tests/test_overlay_adapter.py`
- `acp-relay/tests/test_well_known_resolver.py`
- `acp-sdk-java/src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java`
- `acp-sdk-java/src/test/java/org/acp/client/EnterpriseProfileConfigCompatibilityTest.java`

## Demo / Example Changes

- overlay example service/client scripts added under `examples/`
- quick-start and demo README include overlay-run instructions
- CLI README includes overlay bootstrap (`discover well-known`) usage note

## Blocked / Deferred

No hard blockers in this pass.

Intentionally deferred:

- AWS KMS / cloud-provider expansion
- sender descriptor envelope extension
- non-HTTP overlay adapters
- PKI lifecycle automation

## Recommended Next Step

Implement the next overlay adoption increment as framework-integrated wrappers (for example Spring/Flask middleware packages) while reusing the frozen well-known and enterprise config model from this pass.
