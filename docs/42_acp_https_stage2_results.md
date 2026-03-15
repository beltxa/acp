# ACP HTTPS Hardening Stage 2 Results

Date: 2026-03-15

## What Changed

- Python SDK HTTP paths are now HTTPS-first:
  - direct HTTP delivery (`HTTPTransport`)
  - relay client HTTP calls
  - discovery `.well-known` and relay/directory lookups
- Python relay HTTP paths are now HTTPS-first:
  - relay outbound delivery to recipient endpoints
  - relay discovery lookups via hints and `.well-known`
- ACP CLI now supports HTTPS hardening controls and validation:
  - global flags for insecure/local exception and TLS options
  - `acp config show`
  - `acp config validate`
  - secure/insecure visibility in `agent status`, `transport list`, `transport probe`, and relay inspection output
- Java SDK alignment:
  - HTTP URL security policy enforcement (reject insecure HTTP by default)
  - explicit insecure override support via `AcpAgentOptions`
  - insecure TLS override support via `AcpAgentOptions`

## Default Behavior Changes

- Default policy for HTTP-based ACP paths is now:
  - `allow_insecure_http = false`
  - `allow_insecure_tls = false`
- `http://` endpoints/hints are rejected unless explicit insecure override is enabled.
- HTTPS certificate verification remains enabled by default.

## Override Flags and Settings

Python SDK / CLI:

- `allow_insecure_http` (config)
- `allow_insecure_tls` (config)
- `ca_file` (config)
- CLI flags:
  - `--allow-insecure-http`
  - `--allow-insecure-tls`
  - `--ca-file <path>`

Python relay (env):

- `ACP_ALLOW_INSECURE_HTTP`
- `ACP_ALLOW_INSECURE_TLS`
- `ACP_CA_FILE`

Java SDK (`AcpAgentOptions`):

- `setAllowInsecureHttp(boolean)`
- `setAllowInsecureTls(boolean)`
- `setCaFile(String)`

## Intentional Insecure HTTP Exceptions

The following remain intentionally HTTP for local/demo workflows and are now explicitly override-gated:

- `demo/` run scripts and relay local URL paths
- chess and poker docker-compose local stacks
- python chess-player local startup defaults and compose files

These paths now include explicit insecure override settings/flags (`allow_insecure_http` or transport-specific env flags).

## Migration Notes for Older Configs

Configs/scripts that previously used `http://` without overrides must be updated to one of:

1. move endpoints/hints to `https://`, or
2. explicitly enable insecure local/dev/demo mode

Common updates:

- CLI: add `--allow-insecure-http` for local demo commands
- config JSON: add `"allow_insecure_http": true` only for local/demo
- relay env: set `ACP_ALLOW_INSECURE_HTTP=true` for local demo relay
- Java app properties: set `acp-allow-insecure-http=true` for local/demo stacks

## Follow-Up for Full Certificate Management

- Python SDK currently supports custom CA bundle via `ca_file`.
- Java SDK exposes `caFile` setting but does not yet wire custom CA trust-store loading.
- mTLS, enterprise PKI integration, and certificate pinning remain out of scope for this pass.
