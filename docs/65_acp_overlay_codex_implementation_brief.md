
# ACP Overlay Adapter Implementation Brief for Codex

## Purpose

Implement the first ACP overlay adapter pass.

This pass should make ACP easier to adopt on top of existing services by providing thin wrappers around existing HTTP-based application flows.

The goal is to build the first practical overlay adoption layer after the Well-Known Endpoint.

This is not a full implementation of the broader Overlay Adoption Model.
It is the first concrete adapter pass.

---

## Goal

Add overlay adapter capabilities so developers can introduce ACP to existing HTTP-based services without converting everything into full ACP-native runtimes.

The pass should focus on:

- inbound HTTP overlay handling
- outbound HTTP overlay sending
- well-known-aware discovery bootstrap
- compatibility with current ACP identity and security semantics
- demo/example support

---

## Important Rules

1. Do not redesign ACP core semantics.
2. Do not weaken ACP identity verification or payload security.
3. Reuse existing ACP runtime components where possible.
4. Keep the first overlay pass HTTP(S)-first.
5. Do not implement a huge framework matrix.
6. Keep adapters thin and practical.
7. The pass should complete unless there is a genuine ambiguity or hard blocker.

---

## Required Scope

### 1. Inbound Overlay Adapter
Implement a thin inbound wrapper that can:

- receive HTTP(S) requests
- recognize ACP messages
- verify signatures / decrypt payloads using existing runtime functionality
- pass the business payload to an existing handler
- return ACP-aware responses where relevant

### 2. Outbound Overlay Adapter
Implement a thin outbound helper that can:

- take a business payload
- build ACP envelope/sign/encrypt using existing runtime functionality
- discover target metadata via well-known or explicit hints
- send over HTTP(S)

### 3. Well-Known Integration
The overlay pass must work cleanly with the new `/.well-known/acp` endpoint.

Expected behavior:
- base URL provided
- derive `/.well-known/acp`
- load metadata
- use transport hints for communication

### 4. Demo / Example Rework
Update examples and demo assets so there is at least one clear overlay-mode example showing:

- an existing-style service exposed through an ACP overlay wrapper
- an outbound ACP-over-HTTP call from existing application logic

### 5. CLI / Docs / Validation
Add the minimum docs/examples/CLI support needed to show the overlay path clearly.

This may include:
- docs only
- helper commands if already natural in the CLI
- example configs

Do not overbuild a new control plane.

---

## Suggested Deliverables

### Python
- inbound overlay helper/wrapper
- outbound overlay helper/wrapper
- example usage
- tests

### Java
- equivalent minimal overlay support where practical
- if full symmetry is too large in one pass, implement the smallest useful outbound/inbound path and report the gap clearly

### Demo / Example
- at least one overlay demo/example
- updated README / docs for overlay usage

---

## Testing Expectations

Add focused tests for:
- inbound overlay request handling
- outbound overlay request generation
- well-known bootstrap use in overlay mode
- compatibility with HTTPS-first security posture
- example/demo-level sanity if practical

Keep tests meaningful and bounded.

---

## Out of Scope

Do not implement in this pass:
- full Overlay Adoption Model governance/policy profile
- sender descriptor message extension
- non-HTTP overlay adapters
- framework-specific integrations for many ecosystems
- relay redesign
- new transport bindings

Those can follow later.

---

## Result Document

Generate a result document for review:

```text
docs/68_acp_overlay_adapter_results.md
```

It should include:
- files changed
- adapter APIs/helpers introduced
- demo/example changes
- tests added/updated
- any remaining overlay gaps
- recommended next steps

---

## Working Style

Be aggressive but disciplined.

Prefer:
- one coherent HTTP-first overlay adapter path
- reuse of existing ACP runtime logic
- practical examples

over broad, unfinished generality.
