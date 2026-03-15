# ACP Well-Known Implementation Results

## Summary
Implemented ACP self-describing discovery using `/.well-known/acp` as the primary metadata endpoint across Python SDK, Java SDK, relay discovery resolver, CLI discovery commands, and chess/poker demo HTTP controllers.

The new flow is:
1. fetch `/.well-known/acp`
2. read `identity_document` reference
3. fetch identity document
4. verify identity document signature/validity (SDK discovery clients)
5. continue with ACP trust model

## Files Changed
- `acp-sdk-python/acp/well_known.py`
- `acp-sdk-python/acp/discovery.py`
- `acp-sdk-python/acp/agent.py`
- `acp-sdk-python/acp/__init__.py`
- `acp-sdk-python/acp_cli/discover_commands.py`
- `acp-sdk-python/acp_cli/agent_commands.py`
- `acp-sdk-python/acp_cli/README.md`
- `acp-sdk-python/tests/test_well_known_discovery.py`
- `acp-sdk-python/tests/test_cli_phase1.py`
- `acp-sdk-python/tests/test_discovery_enterprise.py`
- `acp-relay/routing.py`
- `acp-relay/tests/test_well_known_resolver.py`
- `acp-sdk-java/src/main/java/org/acp/client/AcpAgent.java`
- `acp-sdk-java/src/main/java/org/acp/client/DiscoveryClient.java`
- `acp-sdk-java/src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java`
- `tools/chess-player/src/main/java/com/cooperate/chessplayer/service/AcpChessClient.java`
- `tools/chess-player/src/main/java/com/cooperate/chessplayer/api/AcpController.java`
- `tools/poker-demo/player/src/main/java/com/cooperate/poker/player/service/AcpPlayerRuntime.java`
- `tools/poker-demo/player/src/main/java/com/cooperate/poker/player/web/AcpController.java`
- `tools/poker-demo/dealer/src/main/java/com/cooperate/poker/dealer/messaging/AcpDealerOutboundChannel.java`
- `tools/poker-demo/dealer/src/main/java/com/cooperate/poker/dealer/api/AcpController.java`
- `tools/python-chess-player/app/acp_client.py`
- `tools/python-chess-player/app/main.py`
- `examples/run_agent_server.py`
- `tools/chess-player/README.md`
- `tools/python-chess-player/README.md`
- `tools/poker-demo/README.md`
- `docs/10_protocol-summary.md`
- `docs/25_acp_current_implementation_status.md`
- `docs/32_acp_cli_specification.md`
- `docs/34_acp_cli_command_surface.md`

## Design Decisions
- Standardized on `/.well-known/acp` (removed runtime reliance on `/.well-known/acp/agents/{name}`).
- Well-known payload is public metadata only and includes:
  - `agent_id`
  - `identity_document` reference (URL or relative URL)
  - `transports`
  - `version`
  - `security_profile` hint
  - optional capability hints
- Identity document remains authoritative; discovery does not treat well-known metadata as trust root.
- Relative `identity_document` references are resolved against the well-known URL.

## Runtime Changes
### Python SDK
- Added `acp.well_known` helper module for building/parsing well-known metadata.
- `DiscoveryClient` now:
  - queries `/.well-known/acp`
  - resolves/fetches `identity_document`
  - verifies identity document and validity window
  - exposes `resolve_well_known(base_url, expected_agent_id=...)`
- `Agent` now exposes `build_well_known_document(...)`.

### Java SDK
- `DiscoveryClient` now consumes `/.well-known/acp` metadata and resolves identity docs through the metadata reference.
- Added `resolveWellKnown(baseUrl, expectedAgentId)` for explicit well-known queries.
- `AcpAgent` now exposes `buildWellKnownDocument(...)` for HTTP controller integration.

### Relay
- Relay resolver now:
  - queries recipient `/.well-known/acp`
  - resolves the referenced identity document
  - validates expected `agent_id` coherence
- Relay routing snapshot now includes discovery metadata mode.

### CLI
- Added `acp discover well-known <base-url> [--agent-id ...]`.
- Updated local agent-run HTTP listener to publish `/.well-known/acp` metadata using the runtime helper.

## Demo / Tooling Changes
- Updated Java chess and poker ACP controllers to expose `GET /.well-known/acp`.
- Updated Python chess player to expose `GET /.well-known/acp`.
- Updated `examples/run_agent_server.py` to expose `GET /.well-known/acp` and print the well-known URL.
- Updated demo/tool README references from `/.well-known/acp/agents/{name}` to `/.well-known/acp`.

## Tests Added / Updated
- Python:
  - `tests/test_well_known_discovery.py` (new)
  - `tests/test_cli_phase1.py` (new parser + command coverage for `discover well-known`)
  - `tests/test_discovery_enterprise.py` (updated endpoint expectation)
- Relay:
  - `tests/test_well_known_resolver.py` (new)
- Java:
  - `src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java` (new)

## Validation Results
- `PYTHONPATH=acp-sdk-python pytest -q acp-sdk-python/tests` passed (`110 passed`).
- `pytest -q acp-relay/tests` passed (`12 passed`).
- `mvn -q -f acp-sdk-java/pom.xml test` passed.
- `mvn -q -f tools/chess-player/pom.xml test` passed.
- `mvn -q -f tools/poker-demo/pom.xml test` passed.

## Blockers / Ambiguities
- No hard blockers encountered during the original implementation pass.
- This ambiguity was resolved in the later freeze pass: `identity_document` is now URL-reference only (absolute `http(s)` URL or root-relative path), and embedded objects are rejected.

## Deferred Items
- Overlay Adoption Model remains deferred.
- Sender descriptor envelope extension remains deferred.
- No relay-side publication of well-known metadata as a registry substitute was added.

## Recommended Next Steps
- Freeze JSON fixture vectors for `/.well-known/acp` responses and identity-reference combinations.
- Add cross-language interoperability test vectors specifically for malformed well-known metadata handling.
- Keep the URL-reference-only `identity_document` rule as the frozen model going forward.
