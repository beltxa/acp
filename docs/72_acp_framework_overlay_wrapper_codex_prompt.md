# ACP Framework Overlay Wrapper Codex Prompt

Use the attached documents and current codebase as the source of truth.

Implement the next ACP overlay ergonomics pass:
framework-integrated overlay wrappers.

This pass should make ACP materially easier to embed into existing HTTP services.

## Goals

1. Add framework-friendly inbound/outbound overlay support
2. Reuse the already implemented overlay adapter and well-known model
3. Keep HTTPS-first and enterprise profile compatibility intact
4. Produce practical examples for Python and Java services

## Targets

### Python
- Flask
- FastAPI or generic ASGI-compatible approach
- generic WSGI/ASGI wrapper if cleaner

### Java
- Spring Boot / Spring-friendly integration
- servlet-style fallback if simpler

## Important rules

- Do not redesign ACP core semantics
- Do not weaken existing security posture
- Reuse frozen well-known model and enterprise profile
- Keep the pass HTTP(S)-first
- Prefer thin middleware/wrappers over heavy framework code
- Complete the pass unless blocked by a real ambiguity or hard blocker

## Required work

### Step 1 — Python framework overlay wrappers
Implement:
- inbound wrapper / middleware
- outbound helper
- well-known endpoint integration in framework context
- Flask example
- FastAPI or ASGI example if practical

### Step 2 — Java framework overlay wrappers
Implement:
- Spring-friendly inbound integration
- outbound helper
- well-known endpoint integration in framework context where practical
- Spring example

### Step 3 — Docs and examples
Add developer-friendly docs:
- adding ACP to an existing Flask/FastAPI service
- adding ACP to an existing Spring service
- outbound ACP-over-HTTP from existing logic
- using well-known bootstrap

### Step 4 — Tests and hardening
Add focused tests for:
- inbound wrapper behavior
- outbound wrapper behavior
- well-known availability
- HTTPS-first compatibility
- example-level sanity

## Deliverables

At the end, produce:
- implementation updates
- examples
- tests
- `docs/71_acp_framework_overlay_wrapper_results.md`

The results document must summarize:
1. files changed
2. wrapper APIs introduced
3. examples added
4. tests added/updated
5. remaining ergonomics gaps
6. recommended next step

## Out of scope

Do not implement:
- non-HTTP framework integrations
- sender descriptor extension
- AWS KMS provider
- PKI automation
- new transport bindings

## Decision rule

If trade-offs are needed, prefer:
- one coherent reusable wrapper path
- practical developer ergonomics
- security/profile consistency

over broad unfinished framework coverage.
