
# ACP Well-Known Endpoint Codex Prompt

Use the attached documents as the source of truth.

Implement ACP self-describing agent discovery via the standard endpoint:

```text
/.well-known/acp
```

This must be done in **one development phase with two steps**:

## Step 1 — Build and Test
Implement aggressively across:
- Python SDK
- Java SDK
- Python relay
- CLI
- demo / example tooling

## Step 2 — Harden
Tighten and finalize:
- validation
- docs/examples
- status outputs
- security posture
- edge-case handling
- result documentation

Backward compatibility is not a concern.
You may aggressively simplify or rework existing discovery/demo assumptions if that produces a more coherent result.

## Goals

1. Expose `/.well-known/acp` for ACP-capable HTTP(S) agents
2. Make discovery capable of consuming well-known metadata
3. Add CLI support for querying well-known metadata
4. Rework relay/discovery behavior where necessary to align with the new model
5. Rework demo tools/configs/scripts so they match the new discovery path
6. Finish the pass unless there is a genuine ambiguity or hard blocker
7. Generate a result document for later review

## Important rules

- Do not redesign ACP core semantics
- Do not expose secrets in well-known metadata
- Treat well-known metadata as discovery input, not trust root
- Keep identity document and signature verification authoritative
- Do not implement the broader Overlay Adoption Model yet
- Do not implement sender descriptor envelope extension yet

## Deliverables

At the end, produce:

```text
docs/58_acp_well_known_implementation_results.md
```

with:
- files changed
- decisions taken
- runtime/relay/demo changes
- tests added/updated
- blockers or ambiguities
- recommended next steps

## If trade-offs appear

Prefer:
- coherent discovery model
- coherent demo/tooling behavior
- secure public metadata
- practical implementation completion

over preserving older patterns.
