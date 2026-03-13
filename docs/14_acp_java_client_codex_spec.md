
# ACP Java Client Library – Codex Specification and Context
## Minimal Java Library for Existing Poker Agents

## 1. Purpose

Build a **minimal Java ACP client library** so that existing Java poker agents and poker dealer code can communicate over ACP without rewriting the agents in Python.

This is **not** a full Java SDK.
It is a **small protocol client library** that implements only the features needed for the poker demo and early ACP interoperability validation.

---

## 2. Primary Goal

Enable existing Java poker agents to:

- create or load ACP identities
- build encrypted and signed ACP messages
- send ACP `SEND` messages to one or more recipients
- receive and process inbound ACP messages
- produce `ACK` and `FAIL`
- optionally emit `COMPENSATE` messages after partial failure
- communicate with Python ACP agents and/or via a Python ACP relay

---

## 3. Scope

### In scope
- ACP identity loading/generation
- identity document loading
- message envelope model
- protected payload model
- signing and verification
- payload encryption and decryption
- HTTP client transport
- direct send or relay send
- `SEND`, `ACK`, `FAIL`
- message deduplication support
- enough capability handling for interoperability

### Out of scope
- full premium profile
- advanced negotiation
- stateful relay behavior
- event channels
- governance workflows
- full enterprise SDK ergonomics
- blockchain
- MLS or ratcheting

---

## 4. Language and Library Preferences

Use Java suitable for practical project integration.

Preferred choices:
- Java 21+
- Jackson for JSON
- Java HTTP client or OkHttp for transport
- standard Java crypto where practical
- use reliable libraries for Ed25519 / X25519 / AES-GCM if needed

Keep dependencies minimal and sensible.

---

## 5. Design Rule

The Java library must follow the ACP protocol as defined by the Python reference implementation.

It should be:
- small
- readable
- easy to integrate
- protocol-correct

It does **not** need to be feature-complete.

---

## 6. Functional Requirements

### 6.1 Identity
Support:

- `agent_id`
- signing key
- encryption key
- signed identity document
- local load or generation

Suggested API:

```java
AcpAgent agent = AcpAgent.loadOrCreate("agent:dealer@poker.demo");
```

### 6.2 Discovery
Support minimal discovery via:
- local cached identity documents
- static identity document loading
- optional `.well-known` lookup later

For the poker demo, static configuration or local file-based identity resolution is acceptable initially.

### 6.3 Message Classes
Implement:

- `SEND`
- `ACK`
- `FAIL`

Define:
- `COMPENSATE` message structure
- `CAPABILITIES` structure if easy to support

### 6.4 Crypto
Implement:

- Ed25519 signatures
- X25519 content key wrapping or equivalent compatible approach
- AES-256-GCM payload encryption

### 6.5 Transport
Implement:
- direct HTTP POST to recipient endpoint
- HTTP POST to relay endpoint

### 6.6 Deduplication
Provide support for duplicate-safe processing based on `message_id`.

This can initially be lightweight and in-memory.

---

## 7. ACP Message Assumptions

ACP message model:

### Routing Envelope (cleartext)
Must include:
- `acp_version`
- `message_class`
- `message_id`
- `operation_id`
- `timestamp`
- `expires_at`
- `sender`
- `recipients`
- `context_id`
- `crypto_suite`

Optional:
- `correlation_id`
- `in_reply_to`

### Protected Payload (encrypted)
Must contain:
- ciphertext
- IV/nonce
- auth tag
- wrapped content key(s)
- sender signature
- payload hash

Use canonical JSON field naming consistent with the Python prototype.

---

## 8. Suggested Java Package Structure

```text
/acp-sdk-java
  /src/main/java/...
    AcpAgent.java
    Identity.java
    IdentityDocument.java
    DiscoveryClient.java
    MessageEnvelope.java
    ProtectedPayload.java
    CryptoSupport.java
    TransportClient.java
    AckMessage.java
    FailMessage.java
    DedupStore.java
```

---

## 9. Suggested Public API

Example target API:

```java
AcpAgent agent = AcpAgent.loadOrCreate("agent:dealer@poker.demo");

agent.send(
    List.of("agent:player1@poker.demo", "agent:player2@poker.demo"),
    payload,
    "hand-123"
);
```

Possible inbound handling shape:

```java
agent.receive(envelopeJson);
```

Or:
- provide a message parser and let the host application call it

Keep the API simple.

---

## 10. Poker Demo Integration Goal

The Java library only needs to support the poker demo use cases.

Typical flows:
- dealer sends hand start
- dealer sends targeted hole cards
- dealer sends action request
- player sends action response
- dealer broadcasts action applied or table event
- partial recipient failure should be representable

This means the Java ACP client should support:
- one-to-one targeted messages
- one-to-many sends
- protocol acks/fails
- duplicate tolerance

---

## 11. Interoperability Priority

The most important requirement is interoperability with the Python ACP implementation.

Codex should prioritize:
1. shared message format
2. shared crypto encoding
3. compatible base64 handling
4. predictable field names
5. conformance tests using sample messages

If needed, generate fixed test vectors.

---

## 12. Coding Priorities

1. correctness
2. simplicity
3. interoperability
4. low dependency footprint
5. enough usability for demo integration

Do not over-engineer.

---

## 13. Initial Milestones

### Milestone 1
Java model classes for identity and messages

### Milestone 2
Crypto utilities for signing, verification, encryption, decryption

### Milestone 3
HTTP transport client

### Milestone 4
`SEND`, `ACK`, `FAIL`

### Milestone 5
Integration into poker dealer / player code

### Milestone 6
Interop validation with Python agents or Python relay

---

## 14. Codex Prompt Context

Use this exact development mindset:

> Build a minimal Java ACP client library for existing Java poker agents. The library must implement only the ACP features needed for the poker demo and cross-language interoperability with the Python ACP reference implementation. Keep the design small, clean, and protocol-correct. Prefer a practical, readable implementation over a feature-complete SDK.

---

## 15. Summary

This Java library is a **bridge to prove ACP as a real protocol across languages**.

Success criteria:
- Java poker agents can exchange ACP messages
- Python agents or relay can interoperate with them
- the protocol feels language-independent rather than SDK-dependent
