
# ACP Well-Known Discovery Implementation Package

Version: Draft v1

## Purpose

This package defines the implementation scope for the next ACP development pass.

The goal is to implement the ACP Well-Known Endpoint model and integrate it across:

- Python SDK
- Java SDK
- Python relay
- CLI
- demo tooling
- example configs and scripts

This pass intentionally prioritizes **self-describing agents** and **zero-configuration discovery bootstrap**.

It does **not** implement the broader ACP Overlay Adoption Model yet.

Overlay adoption remains a later phase.

---

## Scope Summary

This pass should implement:

1. `/.well-known/acp` endpoint support
2. generation of well-known metadata from runtime configuration
3. discovery support for well-known lookups
4. CLI support for querying well-known endpoints
5. relay integration where relevant
6. demo tool updates to use well-known discovery where appropriate
7. hardening and validation of the resulting design

This pass should also revisit any existing discovery/registration/demo assumptions that should now be driven by well-known metadata.

Because backward compatibility is not a constraint, the implementation may aggressively simplify or realign current behavior.

---

## What Is In Scope

### 1. ACP Well-Known Endpoint

Implement a standard endpoint:

```text
/.well-known/acp
```

Served by ACP-capable agent runtimes where HTTP(S) endpoints exist.

The response should include at minimum:

- `agent_id`
- `identity_document` or equivalent identity metadata reference
- `transports`
- `version`

Optional fields may include:

- `security_profile`
- `relay_hint`
- `capabilities`
- `metadata`

### 2. Discovery Integration

ACP discovery should be able to use the well-known endpoint as a first-class source of agent metadata.

Expected behavior:

- discover via explicit well-known URL
- discover by base URL and derive `/.well-known/acp`
- cache useful metadata
- fall back cleanly if well-known is unavailable

### 3. CLI Support

Add CLI support such as:

- `acp discover well-known <base-url>`
- optional status/inspection support showing well-known metadata
- JSON and human-readable output

### 4. Relay Integration

The relay should be reviewed and updated so that:

- relay-backed discovery remains coherent with well-known discovery
- registry/discovery behavior is not in conflict with the well-known model
- relay demo flows can use well-known metadata where useful
- operator commands reflect the new discovery path where appropriate

This does not require the relay to become the source of truth for well-known metadata.

### 5. Demo / Example Rework

Existing demo assets should be updated as needed so the current demo story can be driven through the new discovery model.

This includes reviewing:

- chess demos
- poker demos
- demo startup scripts
- demo configs
- demo runbooks if materially impacted

### 6. Security / Trust Alignment

The well-known implementation must align with current ACP security principles:

- no secrets exposed
- public metadata only
- HTTPS preferred where HTTP is used in production-like paths
- discovery metadata is helpful but not a trust root
- identity documents and signatures remain authoritative

---

## What Is Explicitly Out of Scope

This pass should **not** implement:

- the full ACP Overlay Adoption Model
- sender descriptor extension in the message envelope
- AWS KMS provider
- additional transport bindings
- PKI lifecycle automation
- non-HTTP well-known equivalents for other transports

Those are later phases.

---

## Design Principles

1. Well-known metadata should be compact and public.
2. Well-known discovery should reduce friction, not add a new mandatory control plane.
3. Existing ACP identity and trust semantics must remain intact.
4. Runtime behavior should remain aggressive but coherent; do not preserve older patterns if they conflict with the new model.
5. Demo and tooling should be updated in the same pass so the system is internally consistent.

---

## Recommended Response Shape

Example:

```json
{
  "agent_id": "agent:ricardo.chess@demo",
  "identity_document": "https://agent.example.com/identity.json",
  "transports": {
    "http": {
      "endpoint": "https://agent.example.com/acp",
      "security_profile": "mtls"
    },
    "relay": {
      "endpoint": "https://relay.example.com"
    }
  },
  "version": "1.0",
  "capabilities": [
    "capabilities_request",
    "relay_routing",
    "multi_recipient_send"
  ]
}
```

The exact response may be refined during implementation, but it should remain compact and public.

---

## Runtime Expectations

### Python SDK
- expose `/.well-known/acp` if agent runtime serves HTTP(S)
- derive metadata from current config and identity
- integrate with discovery logic

### Java SDK
- provide equivalent runtime capability where practical
- align discovery behavior and any server/runtime support as closely as possible with Python

### Relay
- align registry/discovery behavior with well-known discovery
- do not conflict with the new metadata source
- update operator visibility if helpful

### CLI
- first-class well-known discovery command
- visible output for security profile / transports / identity references

---

## Demo / Tooling Expectations

The implementation should rework demo tooling and scripts as needed so that:

- agents can be discovered via well-known metadata
- the relay and demos do not depend on outdated discovery assumptions
- the current demo stack remains coherent after the change

Because compatibility is not a concern, cleanup and simplification are encouraged.

---

## Two-Step Execution Model

This work should be executed as one phase with two steps.

### Step 1 — Build and Test
Implement the feature set aggressively and get the system working end to end.

Deliver:
- runtime support
- CLI support
- relay adjustments
- demo/tooling updates
- tests

### Step 2 — Harden
After the feature works, tighten:
- validation
- docs/examples
- status outputs
- security posture
- edge-case handling
- result summary

The implementation should complete unless there is a real ambiguity or hard blocker.

---

## Required Result Document

The pass should generate a result document for later review, containing:

- files changed
- design decisions made
- runtime behavior changes
- relay/demo/tooling changes
- tests added/updated
- anything deferred due to blocker/ambiguity
- recommended next steps

Suggested filename:

```text
docs/58_acp_well_known_implementation_results.md
```
