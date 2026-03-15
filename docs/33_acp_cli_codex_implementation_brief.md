# ACP CLI Implementation Brief for Codex

## Purpose

Implement the first usable version of the ACP CLI.

The CLI must work for both:

- client / agent side workflows
- relay / operator side workflows

This is a thin operational wrapper around the existing ACP SDKs and relay services. It must not become a separate protocol implementation.

The goal is to make ACP:

- easier to demo
- easier to operate
- easier to troubleshoot
- easier to register, discover, and run agents

---

## Implementation Objective

Build a practical ACP CLI v1 that provides the minimum command set needed for:

1. identity creation and inspection
2. discovery and registration
3. running agents
4. sending test messages
5. relay inspection and ops visibility
6. demo support

The CLI should be suitable for:

- local development
- demos with external users
- lightweight operational support
- troubleshooting transport and relay behavior

---

## Design Rules

1. The CLI must call existing SDK / relay functionality where possible.
2. Do not duplicate ACP protocol logic in the CLI.
3. Keep the first version small and scriptable.
4. Prefer stable protocol concepts over implementation details.
5. Support both human-readable and JSON output.
6. Do not expose decrypted payloads in relay/operator commands.
7. Do not print private keys by default.
8. Keep command names predictable and composable.
9. Prefer `https://` for HTTP-based endpoints; allow `http://` only by explicit local/dev/demo exception.

---

## Command Structure

Executable name:

```text
acp
```

General structure:

```text
acp <domain> <command> [options]
```

Main domains for v1:

- identity
- discover
- register
- agent
- message
- transport
- relay
- ops
- config

---

## Scope for CLI v1

### In scope

### Client-side
- `acp identity create`
- `acp identity show`
- `acp identity export`
- `acp identity verify`
- `acp discover get`
- `acp discover list`
- `acp register put`
- `acp register update`
- `acp register show`
- `acp message send`
- `acp message capabilities`
- `acp agent run`
- `acp agent status`
- `acp transport list`
- `acp transport probe`

### Relay-side
- `acp relay run`
- `acp relay status`
- `acp relay health`
- `acp relay registry list`
- `acp relay registry show`
- `acp relay routes show`
- `acp relay ops stats`
- `acp relay ops failures`

### Shared
- `acp config show`
- `acp config validate`
- `acp ops logs`
- `acp ops metrics`

---

## Out of scope for v1

Do not implement yet:

- full enterprise admin plane
- role-based access control
- secret vault integration
- stateful relay governance controls
- billing controls
- advanced demo orchestration
- full TUI/GUI
- remote mutation of all relay internals
- event-channel management
- full lifecycle automation for every transport

---

## Preferred Implementation Shape

### Python first
Implement the first ACP CLI in Python.

Reason:
- fastest implementation path
- matches current SDK and relay stack
- best for demos and local operations

Use the CLI as the primary operational front-end for:
- Python SDK
- Python relay
- demo workflows

Later, Java-side support can remain runtime-driven rather than requiring a separate CLI.

---

## Suggested Repository Placement

Recommended new repository or module location:

```text
/acp-cli-python
```

Or inside the existing Python SDK project if that is simpler:

```text
/acp-sdk-python
  /acp_cli
```

Suggested modules:

```text
acp_cli/
  main.py
  identity_commands.py
  discover_commands.py
  register_commands.py
  agent_commands.py
  message_commands.py
  transport_commands.py
  relay_commands.py
  ops_commands.py
  config_commands.py
  output.py
  common.py
```

---

## CLI Behavior Requirements

## 1. Identity Commands

### Create identity

```text
acp identity create --agent-id agent:john.chess@demo
```

Must:
- create signing key
- create encryption key
- create identity document
- store files locally

### Show identity

```text
acp identity show --agent-id agent:john.chess@demo
```

Must display:
- agent id
- trust profile
- public keys
- transport hints
- file location if useful

### Export identity

```text
acp identity export --agent-id agent:john.chess@demo --out john.identity.json
```

### Verify identity

```text
acp identity verify --file john.identity.json
```

Must validate:
- document structure
- signature
- required fields
- validity window

---

## 2. Discovery Commands

### Discover agent

```text
acp discover get --agent-id agent:ricardo.chess@demo
```

Must:
- resolve using current discovery logic
- display identity and transport hints
- optionally return JSON

### Show cache

```text
acp discover list
```

Must show locally cached discovery entries.

---

## 3. Registration Commands

### Register with relay/directory

```text
acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net
```

Must publish:
- identity document
- current transport hints
- endpoint or relay mode

### Update registration

```text
acp register update --agent-id agent:ricardo.chess@demo --endpoint https://aws-chess.acp-demo.net/acp
```

### Show registration

```text
acp register show --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net
```
---
### Current Relay API Limitation

The current relay implementation exposes only a minimal registration interface.

In CLI v1:

- `register put` and `register update` both publish identity documents through the same relay registration endpoint.
- `register show` resolves registration information through relay-backed discovery (`discover`) rather than a dedicated registry query API.

This approach is intentional for the early ACP phase:

- it minimizes relay complexity
- it supports demos and developer workflows
- it avoids prematurely designing a full relay control plane

Codex should treat this behavior as **correct for v1**.

Future versions of the relay may introduce explicit registry management APIs, but the CLI command surface should remain stable.
---

## 4. Agent Commands

### Run agent

```text
acp agent run --agent-id agent:john.chess@demo
```

Should:
- start local listener(s)
- load config
- activate selected transports
- run message handler loop

### Show status

```text
acp agent status --agent-id agent:john.chess@demo
```

Should show:
- active transports
- current registration state
- listener endpoints
- last activity if available

---

## 5. Message Commands

### Send message

```text
acp message send \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo \
  --payload-file move.json \
  --context chess-game-1
```

Must support:
- one or more recipients
- payload file or inline JSON
- optional transport override
- optional expiry

### Capabilities request

```text
acp message capabilities --from agent:john.chess@demo --to agent:ricardo.chess@demo
```

---

## 6. Transport Commands

### Show transports

```text
acp transport list --agent-id agent:john.chess@demo
```

### Probe transport

```text
acp transport probe --agent-id agent:ricardo.chess@demo --transport mqtt
```

Should verify:
- hint exists
- endpoint/broker reachable if possible
- useful transport metadata can be resolved

---

## 7. Relay Commands

### Run relay

```text
acp relay run --config relay.yaml
```

### Relay status

```text
acp relay status
```

### Relay health

```text
acp relay health
```

### Registry list/show

```text
acp relay registry list
acp relay registry show --agent-id agent:ricardo.chess@demo
```

### Route inspection

```text
acp relay routes show --agent-id agent:ricardo.chess@demo
```

### Ops stats/failures

```text
acp relay ops stats
acp relay ops failures
```

Relay commands must not show decrypted payload content.

---

## 8. Output Modes

All major commands should support:

### Human-readable output
Default output for interactive use.

### JSON output
For automation and scripting.

Example:

```text
acp relay status --json
```

Implement a consistent output abstraction.

---

## 9. Security Requirements

The CLI must not:

- print private keys by default
- expose decrypted relay payloads
- silently bypass identity checks
- silently switch transports without making it visible

Any local-development bypass should require an explicit flag, such as:

```text
--allow-insecure-local-dev
```

---

## 10. Suggested Libraries

Codex may use a practical Python CLI framework such as:

- `argparse` for low dependency footprint
- or `typer` if already suitable and available

Prefer minimal complexity.

If using a framework, keep the command tree simple and readable.

---

## 11. Recommended Phased Implementation

### Phase 1 — Core CLI skeleton
- main entrypoint
- command tree
- output formatting
- config loading

### Phase 2 — Identity and discovery
- identity create/show/export/verify
- discover get/list

### Phase 3 — Registration and messaging
- register put/update/show
- message send
- capabilities request

### Phase 4 — Agent and transport
- agent run
- agent status
- transport list/probe

### Phase 5 — Relay operations
- relay run/status/health
- relay registry list/show
- relay routes show
- relay ops stats/failures

### Phase 6 — Hardening
- JSON output consistency
- error handling
- docs and examples
- smoke tests

---

## 12. Testing Expectations

Codex should add tests for:

- command parsing
- JSON output correctness
- identity creation flow
- discovery output
- registration command behavior
- send command invocation
- relay status/health output
- error paths and missing-argument handling

Use lightweight tests first.

---

## 13. Documentation Deliverables

Codex should also provide:

1. CLI README or usage guide
2. examples for key commands
3. note on security-sensitive behavior
4. quick-start examples for:
   - identity creation
   - registration
   - direct send
   - relay inspection

---

## 14. Working Rule for Codex

Implement the CLI as the thinnest possible layer over the existing ACP runtime and SDK functionality.

Do not re-implement ACP protocol logic inside the CLI.

If a needed runtime hook is missing, add the smallest required internal API to expose the capability cleanly.

---

## 15. Success Criteria

ACP CLI v1 is successful when a user can:

- create an identity
- discover another agent
- register with a relay
- send a test ACP message
- run an agent locally
- inspect relay status and registry
- troubleshoot basic transport issues

without touching Python internals or raw SDK code.
