# Codex Context Prompt for ACP Initial Development

You are implementing the first reference version of the **Agent Communication Protocol (ACP)**.

Use the attached **ACP Codex Engineering Brief** as the main source of truth.

## Your mission

Build a minimal but real ACP reference implementation that proves the protocol and is suitable for early developer adoption.

## Product goal

ACP is a secure, transport-agnostic protocol for communication between autonomous software agents.

The first implementation must demonstrate:

- agent identity creation
- identity document generation
- domain-style discovery
- encrypted and signed ACP messages
- one-to-one and one-to-many messaging
- a simple relay service
- protocol-level `ACK` and `FAIL`
- a simple developer SDK with a clean `send()` API

## Important constraints

- Do **not** build the full enterprise platform.
- Do **not** build premium governance or compliance features.
- Do **not** introduce unnecessary architectural complexity.
- Do **not** use blockchain.
- Do **not** implement MLS or ratcheting in the first version.
- Prefer simple, explicit code over abstraction-heavy frameworks.

## Protocol assumptions

- Identity uses `agent_id` plus signing and encryption keys.
- Use signed identity documents.
- Discovery order: cache, `.well-known`, relay hints.
- Message structure: routing envelope + encrypted protected payload.
- Use hybrid encryption:
  - payload encrypted once with symmetric key
  - content key wrapped separately for each recipient
- Recommended algorithms:
  - Ed25519 for signatures
  - X25519 for encryption/key agreement
  - AES-256-GCM for payload encryption

## Core message classes to implement

- `SEND`
- `ACK`
- `FAIL`
- `CAPABILITIES`
- define `COMPENSATE` structure even if initial processing is minimal

## Preferred implementation approach

### Language
Prefer **Python** for the first reference implementation.

### Deliverables
Build:
1. ACP Python SDK
2. Minimal HTTP relay service
3. Example agents / demo scripts
4. Basic documentation

## Suggested repository structure

```text
/acp-sdk-python
/acp-relay
/examples
/docs
```

## Engineering priorities

1. protocol correctness
2. clean developer experience
3. readable code
4. simple local execution
5. examples that prove the concept

## Examples to support

- one agent sends to one agent
- one agent sends to multiple agents
- recipient returns `ACK`
- recipient returns `FAIL`
- sender emits `COMPENSATE` after partial failure
- simple capability advertisement example

## Working rule

If a design choice is unclear, choose the smallest solution that preserves the ACP protocol model.

Do not over-engineer the first implementation.
