# ACP CLI Specification
Version: Draft v1

## 1. Purpose

This document defines a command-line interface for ACP that can be used on both:

- client / agent side
- relay / operator side

The CLI has two goals:

1. make ACP easy to try and demo
2. provide minimal operational and management capability without introducing a full control plane

The CLI is intended to support:

- developer workflows
- local testing
- demo execution
- light operational support
- registration and discovery tasks
- relay inspection and troubleshooting

It is not intended to replace future enterprise administration tooling.

---

## 2. Design Principles

The ACP CLI should be:

- simple
- scriptable
- transport-aware
- identity-aware
- safe for demos and light operations
- consistent between client and relay contexts

The CLI should expose protocol concepts rather than internal implementation details where possible.

HTTPS posture for HTTP-based ACP paths:

- CLI guidance should prefer `https://` endpoints by default
- plain `http://` should be treated as local/dev/demo exception with explicit opt-in
- optional enterprise profile: HTTP mTLS (`mtls_enabled`, `ca_file`, `cert_file`, `key_file`)

---

## 3. Command Structure

Recommended executable name:

```text
acp
```

Top-level structure:

```text
acp <domain> <command> [options]
```

Suggested domains:

- identity
- discover
- register
- agent
- message
- transport
- relay
- ops
- demo
- config

---

## 4. Client-Side Commands

## 4.1 Identity Commands

### Create identity

```text
acp identity create --agent-id agent:john.chess@demo
```

Creates:
- signing key
- encryption key
- local identity document

Options:
- `--agent-id`
- `--out-dir`
- `--trust-profile`
- `--overwrite`

---

### Show identity

```text
acp identity show --agent-id agent:john.chess@demo
```

Displays:
- agent id
- public keys
- trust profile
- transports
- validity dates

---

### Export identity document

```text
acp identity export --agent-id agent:john.chess@demo --out john.identity.json
```

---

### Verify identity document

```text
acp identity verify --file john.identity.json
```

Verifies:
- document signature
- required fields
- validity window

---

## 4.2 Discovery Commands

### Discover agent

```text
acp discover get --agent-id agent:ricardo.chess@demo
```

Performs discovery using:
1. cache
2. `.well-known`
3. relay/directory if configured

Outputs:
- identity summary
- available transports
- endpoint / relay hints

---

### Discover well-known metadata

```text
acp discover well-known https://ricardo.example.net --agent-id agent:ricardo.chess@demo
```

Fetches and validates:
- `/.well-known/acp` metadata
- referenced identity document

Outputs:
- well-known URL
- security profile hint
- transport hints
- resolved identity summary

---

### Show discovery cache

```text
acp discover list
```

---

## 4.3 Registration Commands

### Register agent with relay or directory

```text
acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net
```

Publishes:
- identity document
- transport hints
- current endpoint/relay mode

Options:
- `--relay`
- `--endpoint`
- `--transport http|relay|amqp|mqtt`
- `--broker`
- `--topic`
- `--exchange`
- `--qos`

---

### Update registration

```text
acp register update --agent-id agent:ricardo.chess@demo --endpoint https://aws-chess.acp-demo.net/acp
```

---

### Remove registration

```text
acp register delete --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net
```

---

### Show registration

```text
acp register show --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net
```
---
### Relay Registration API Note (v1)

In the current ACP CLI v1 implementation, relay registration operations are backed by a minimal relay API.

Operational behavior:

- `acp register put` and `acp register update` both publish registration data using the same relay endpoint.
- `acp register show` resolves registration state using the relay’s discovery endpoint rather than a dedicated registry read API.

This design is sufficient for:

- demos
- developer workflows
- lightweight operational use

However, it should not be interpreted as a full relay administration interface.

Future ACP relay versions may introduce explicit registry management APIs such as:

- `PUT /registry`
- `GET /registry/<agent>`
- `LIST /registry`
- `DELETE /registry/<agent>`

The CLI command structure has been designed so that these APIs can be added later without breaking existing commands.
---

## 4.4 Agent Commands

### Run agent process

```text
acp agent run --agent-id agent:john.chess@demo
```

Runs:
- local listener
- selected transports
- configured handlers

Options:
- `--transport http`
- `--transport amqp`
- `--transport mqtt`
- `--relay`
- `--port`
- `--config`

---

### Show agent status

```text
acp agent status --agent-id agent:john.chess@demo
```

Shows:
- running state
- active transports
- last message timestamps
- current endpoint / relay registration

---

## 4.5 Message Commands

### Send message

```text
acp message send \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo \
  --payload-file move.json \
  --context chess-game-1
```

Supports:
- one or more recipients
- direct or transport-selected delivery
- optional delivery mode override

Options:
- `--from`
- `--to` (repeatable)
- `--payload-file`
- `--payload-json`
- `--context`
- `--transport`
- `--delivery-mode`
- `--expires-in`

---

### Send capabilities request

```text
acp message capabilities --from agent:john.chess@demo --to agent:ricardo.chess@demo
```

---

### Send compensate message

```text
acp message compensate --from agent:dealer@poker.demo --operation-id op-123 --to agent:player1@poker.demo
```

---

## 4.6 Transport Commands

### Show available transports

```text
acp transport list --agent-id agent:john.chess@demo
```

---

### Test transport reachability

```text
acp transport probe --agent-id agent:ricardo.chess@demo --transport mqtt
```

Checks:
- discovery hints present
- endpoint/broker reachable
- auth/config appears valid

---

## 5. Relay-Side Commands

Recommended relay executable:

```text
acp relay <command> [options]
```

Or shared executable style:

```text
acp relay <command>
```

## 5.1 Relay Lifecycle

### Run relay

```text
acp relay run --config relay.yaml
```

Starts relay process.

---

### Show relay status

```text
acp relay status
```

Shows:
- running state
- bound transports
- queue/exchange/topic config
- registered agents count
- health state

---

### Health check

```text
acp relay health
```

Outputs:
- ok / degraded / failed
- dependency checks
- broker connectivity
- local message backlog indicators if applicable

---

## 5.2 Relay Registration and Directory Commands

### List registered agents

```text
acp relay registry list
```

---

### Show registered agent

```text
acp relay registry show --agent-id agent:ricardo.chess@demo
```

Displays:
- identity summary
- transport hints
- current reachability
- registration timestamps

---

### Register agent manually

```text
acp relay registry put --file ricardo.identity.json
```

Useful for ops or demo seeding.

---

### Update agent registration

```text
acp relay registry update --agent-id agent:ricardo.chess@demo --endpoint https://aws-chess.acp-demo.net/acp
```

---

### Delete registration

```text
acp relay registry delete --agent-id agent:ricardo.chess@demo
```

---

## 5.3 Relay Routing and Transport Inspection

### Show relay routes

```text
acp relay routes list
```

---

### Show route for agent

```text
acp relay routes show --agent-id agent:ricardo.chess@demo
```

Displays:
- preferred direct path
- relay path
- AMQP fallback hints
- MQTT fallback hints

---

### Test route resolution

```text
acp relay routes probe --agent-id agent:ricardo.chess@demo
```

---

## 5.4 Relay Operational Commands

### Show recent messages

```text
acp relay ops messages --limit 20
```

Shows metadata only:
- message id
- sender
- recipient
- transport used
- outcome

Never show decrypted payload.

---

### Show failures

```text
acp relay ops failures --limit 20
```

Shows:
- routing failures
- expiry failures
- transport delivery failures
- downstream errors

---

### Show stats

```text
acp relay ops stats
```

Outputs:
- total messages routed
- messages per transport
- ACK / FAIL counts
- duplicate detections if tracked
- direct vs relay vs fallback counts

---

### Drain / maintenance mode

```text
acp relay ops maintenance on
acp relay ops maintenance off
```

Purpose:
- controlled demo operations
- maintenance windows
- temporary stop to new registrations or routing attempts

---

## 6. Shared Operational Commands

## 6.1 Configuration

### Show effective config

```text
acp config show
```

---

### Validate config

```text
acp config validate --file config.yaml
```

---

## 6.2 Logs

### Tail logs

```text
acp ops logs --follow
```

Filters:
- `--agent-id`
- `--message-id`
- `--transport`
- `--level`

---

## 6.3 Metrics Snapshot

```text
acp ops metrics
```

Outputs minimal operational metrics:
- send count
- receive count
- ACK count
- FAIL count
- duplicate count
- transport counts

---

## 7. Demo Commands

These are optional but useful for presentations.

### Seed demo identities

```text
acp demo seed chess
```

Creates:
- `agent:john.chess@demo`
- `agent:ricardo.chess@demo`

---

### Start chess demo

```text
acp demo chess --mode direct
acp demo chess --mode relay
acp demo chess --mode amqp
acp demo chess --mode mqtt
```

---

### Start poker demo

```text
acp demo poker --mode direct
acp demo poker --mode relay
acp demo poker --mode amqp
acp demo poker --mode mqtt
```

These commands may simply wrap lower-level config and launch steps.

---

## 8. Security Rules for the CLI

The CLI must not:
- print private keys by default
- expose decrypted payloads in relay ops mode
- silently change transport without logging it
- bypass identity verification unless explicitly forced for local dev mode

For HTTP-based paths, the CLI should:

- prefer HTTPS endpoint examples by default
- require explicit insecure override flags for `http://` in local/dev/demo workflows

Sensitive operations should require explicit flags, for example:

```text
--allow-insecure-local-dev
```

---

## 9. Output Modes

The CLI should support:

- human-readable output (default)
- JSON output for scripting

Example:

```text
acp relay status --json
```

This is important for automation.

---

## 10. Recommended Minimum v1 Command Set

If scope must be minimized, implement these first.

### Client minimum
- `acp identity create`
- `acp identity show`
- `acp discover get`
- `acp discover well-known`
- `acp register put`
- `acp register update`
- `acp message send`
- `acp agent run`
- `acp agent status`

### Relay minimum
- `acp relay run`
- `acp relay status`
- `acp relay registry list`
- `acp relay registry show`
- `acp relay routes show`
- `acp relay ops stats`
- `acp relay ops failures`

---

## 11. Suggested Implementation Notes

The CLI should be implemented as a thin wrapper around existing SDK and relay APIs, not as a separate protocol implementation.

That means:
- client-side CLI calls SDK services
- relay-side CLI calls relay management and registry interfaces
- output formatting is layered on top

This keeps behavior consistent with the runtime.

---

## 12. Summary

The ACP CLI should make ACP usable operationally without requiring a full management platform.

It should support:
- identity
- discovery
- registration
- messaging
- transport inspection
- relay operations
- demos

while preserving ACP’s protocol-first and low-friction philosophy.
