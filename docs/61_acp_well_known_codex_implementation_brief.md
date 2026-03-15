
# ACP Well-Known Endpoint Implementation Brief for Codex

## Purpose

Implement ACP self-describing agent discovery based on the standard HTTP(S) endpoint:

```text
/.well-known/acp
```

This pass should integrate the feature across runtimes, relay, CLI, and demo tooling.

This is a single development phase executed in two steps:
1. build and test
2. harden

Backward compatibility is not a concern in this pass.

Aggressive cleanup and alignment are allowed.

---

## Primary Goal

Make ACP agents discoverable through a simple, standard, self-describing endpoint so that agent-to-agent interaction can bootstrap with minimal prior configuration.

This is the first implementation step toward lower-friction ACP adoption.

The broader Overlay Adoption Model is not being implemented in this pass.

---

## Required Work

### 1. Well-Known Endpoint
Implement `/.well-known/acp` support in the relevant runtimes.

The endpoint should publish public metadata only:
- agent id
- identity metadata reference
- transports
- security profile hint
- version
- optional capabilities

### 2. Discovery Logic
Extend discovery so ACP can:
- resolve from a base URL via `/.well-known/acp`
- parse and cache well-known metadata
- use it to guide communication

### 3. CLI Support
Add CLI support such as:
- `acp discover well-known <base-url>`

Output should support:
- human-readable mode
- JSON mode

### 4. Relay Review and Rework
Review and update relay behavior so that:
- registry/discovery flows remain coherent with well-known discovery
- operator inspection commands remain accurate
- old discovery assumptions can be simplified if needed

### 5. Demo / Example Rework
Rework demo tools, configs, and scripts so they remain internally consistent with the new well-known discovery model.

This includes current chess/poker/demo assets where relevant.

### 6. Docs / Validation / Status
After implementation works, harden:
- docs
- examples
- config validation
- CLI/status outputs
- test coverage

---

## Design Rules

1. Do not redesign ACP core identity, discovery trust model, or message semantics.
2. Well-known metadata must not expose secrets.
3. Well-known metadata is useful discovery input, not a trust root.
4. Existing identity document and signature verification remain authoritative.
5. Backward compatibility is not required; coherence is more important.
6. Overlay-mode features beyond well-known discovery are explicitly deferred.

---

## Suggested Metadata Fields

At minimum:
- `agent_id`
- `identity_document`
- `transports`
- `version`

Optional:
- `security_profile`
- `relay_hint`
- `capabilities`
- `metadata`

---

## Step 1 — Build and Test

Implement aggressively across:
- Python SDK
- Java SDK
- Python relay
- CLI
- demo tooling

Expected outputs:
- working well-known endpoint
- working discovery support
- working CLI command
- updated relay/demo behavior
- passing tests

---

## Step 2 — Harden

Tighten:
- validation
- output quality
- docs
- examples
- error handling
- security posture
- result summary

---

## Testing Expectations

Add or update tests for:
- endpoint serving behavior
- discovery parsing behavior
- invalid/missing well-known metadata
- CLI well-known query behavior
- relay interactions where relevant
- demo flow compatibility if testable
- secure/insecure endpoint handling where relevant

Keep tests practical and meaningful.

---

## Required Result Document

Generate:

```text
docs/58_acp_well_known_implementation_results.md
```

It should include:
1. files changed
2. design decisions taken
3. runtime behavior changes
4. relay changes
5. demo/tooling changes
6. tests added/updated
7. any blockers or ambiguities
8. recommended next steps

---

## Out of Scope

Do not implement:
- full Overlay Adoption Model
- sender descriptor envelope extension
- AWS KMS provider
- new transport bindings
- PKI lifecycle automation
- non-HTTP well-known discovery standards

Those come later.
