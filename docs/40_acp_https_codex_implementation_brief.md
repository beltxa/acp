# ACP HTTPS Hardening Codex Implementation Brief

## Purpose

Implement HTTPS hardening for ACP HTTP-based transport paths.

This is a transport/configuration hardening task, not a protocol redesign.

ACP already encrypts payloads at the protocol layer. This work makes HTTP-based deployments acceptable to security reviewers by using HTTPS by default.

---

## Objective

Update the ACP codebase so that:

- HTTPS is the default for HTTP-based ACP endpoints
- insecure HTTP is allowed only by explicit override
- discovery and registration examples prefer HTTPS
- relay and direct endpoint configs support HTTPS cleanly
- CLI/config validation surfaces insecure transport clearly

This must apply to:

- Python SDK
- Java SDK where relevant
- Python relay
- CLI/config validation
- demo configs and examples

---

## Important Rules

1. Do not redesign ACP protocol semantics.
2. Do not change ACP identity, discovery, or encryption models.
3. Treat this as a transport hardening pass.
4. Prefer minimal, explicit implementation changes.
5. Keep local/dev/demo insecure options available, but never implicit.
6. Emit warnings or validation failures for insecure HTTP unless explicitly allowed.

---

## Implementation Scope

### 1. Direct HTTP transport
Update direct HTTP transport handling so that:

- `https://` is preferred by default
- plain `http://` requires explicit insecure allowance in non-local contexts
- certificate validation is enabled by default

### 2. Relay HTTP endpoints
Update relay client/server configs and examples to prefer HTTPS endpoints.

### 3. Discovery / registration hints
Ensure examples, config generation, and docs prefer HTTPS URLs for:
- agent HTTP endpoints
- relay endpoints
- discovery endpoints where applicable

### 4. CLI / config validation
Update CLI/config validation so that:
- insecure HTTP endpoints are flagged
- optional explicit overrides exist for demo/dev use
- output clearly indicates whether transport is secure or insecure

### 5. Demo assets
Update demo configs and quick-start examples so HTTPS is the normal recommendation.
If any demo still uses HTTP, it should be clearly marked as demo-only or local-only.

---

## Recommended Runtime Flags / Settings

Codex may introduce the smallest clean settings needed, such as:

- `allow_insecure_http`
- `allow_insecure_tls`
- `ca_file`
- `cert_file`
- `key_file`

Use existing configuration patterns where possible.
Do not create a large TLS management framework.

---

## Specific Implementation Tasks

### Python SDK
- ensure HTTP transport client supports HTTPS cleanly
- add explicit insecure override handling
- add CA file / certificate options only if cleanly supportable
- surface secure/insecure status in config or transport reporting where useful

### Java SDK
- align HTTP client behavior with HTTPS-by-default expectations
- support explicit insecure override only where necessary for dev/demo
- keep implementation small and practical

### Python Relay
- ensure relay can be configured with HTTPS endpoint expectations
- update registration/discovery examples to advertise HTTPS
- do not introduce an enterprise-grade certificate management system

### CLI
- `config validate` should flag insecure HTTP endpoints
- transport/agent output should make secure vs insecure transport visible
- demo-facing commands/docs should prefer HTTPS examples

---

## Out of Scope

Do not implement:
- mandatory mTLS
- enterprise PKI integration
- certificate pinning frameworks
- full secret management system
- full production ingress stack automation
- HTTP transport redesign
- changes to ACP wire format

---

## Testing Expectations

Add or update tests for:

- HTTPS endpoint acceptance
- insecure HTTP rejection/warning by default
- explicit insecure override behavior
- config validation of insecure endpoints
- discovery/registration hint handling with HTTPS URLs
- relay/client handling of secure endpoint configuration

Keep tests focused and lightweight.

---

## Documentation Deliverables

Update or create the minimum necessary docs:

1. HTTPS hardening note reflected in docs/examples
2. quick-start examples updated to prefer HTTPS
3. demo config notes updated
4. any new config flags documented briefly

---

## Working Rule

Implement the smallest clean hardening pass that makes ACP HTTP-based paths HTTPS-first without disturbing core ACP behavior.

If a clean local/demo exception path is needed, make it explicit and visible.

