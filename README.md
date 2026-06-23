## ACP — Agent Communication Protocol
ACP (Agent Communication Protocol) is a secure, identity-driven protocol for autonomous systems to communicate, collaborate, and coordinate across environments.
Unlike traditional API integrations or message brokers, ACP is designed for AI agents operating in dynamic, distributed ecosystems.
This project is not related to other packages using the acronym "ACP"

**HTTP is for services. ACP is for agents.**

## What is ACP?

ACP provides:
 - Identity-first communication between agents
 - Signed and optionally encrypted message envelopes
 - Transport independence (HTTP, AMQP, MQTT)
 - Relay-based routing across network boundaries
 - Capability-driven interaction patterns

This enables agents to discover each other, exchange messages, and collaborate without tight coupling.
ACP SDKs across languages are interoperable and implement the same protocol semantics.

## What ACP Is Not

- Not a message broker.
- Not a JSON schema format.
- Not a framework-specific tool protocol.

## Why ACP?
Modern systems are evolving from services into autonomous agents.
Current approaches (REST APIs, webhooks, point-to-point messaging) lead to:
 - brittle integrations
 - hidden coupling
 - limited interoperability
 - lack of governance

ACP introduces a protocol layer for agent communication, similar to how HTTP enabled the web.

## When to Use ACP

Use ACP when:

- autonomous agents need to communicate across teams, runtimes, or network boundaries
- identity and message verification are required at the protocol level
- you want one protocol across direct and relay delivery paths

ACP may be unnecessary when:

- one application calls one service with stable, tightly controlled APIs
- plain HTTP/REST already solves the integration with low coordination overhead

## ACP vs Typical Approaches

| Approach | Good fit | Gaps for autonomous agent communication |
| --- | --- | --- |
| REST APIs | stable service-to-service calls | endpoint coupling and custom identity/discovery conventions |
| Webhooks | event callbacks | delivery and trust rules vary by implementation |
| Message brokers | high-throughput internal messaging | broker-specific semantics, no shared agent protocol layer |
| Agent tool protocols | tool invocation inside one framework | often framework-scoped, not cross-runtime protocol contracts |
| ACP | cross-agent protocol with identity + secure envelopes | adds protocol concepts not needed for trivial single-service cases |

## SDK Installation Parity

Status labels used in this repo:
- `Published`
- `Available from repo`
- `Experimental`
- `Bridge-based`
- `Coming`

| SDK | Status |
| --- | --- |
| Python (`acp-runtime`) | `Published`|
| TypeScript (`acp-runtime`) | `Published`| 
| Rust (`acp-runtime`) | `Published`|
| Go (`github.com/beltxa/acp/sdks/go`) | `Available from repo`|
| Java (`tech.co-operate:acp-runtime`) | `Published` |
| Mojo wrapper (`acp-sdk-mojo`) | `Bridge-based` |

No SDK in this repository snapshot is currently labeled `Coming`.

## Install ACP

ACP is available across multiple language runtimes.

### Python runtime

```bash
pip install acp-runtime==0.1.6
```

### ACP CLI

```bash
pip install acpctl==0.1.6
```

### TypeScript runtime

```bash
npm install acp-runtime@0.1.6
```

### Java runtime (Maven)

```xml
<dependency>
  <groupId>tech.co-operate</groupId>
  <artifactId>acp-runtime</artifactId>
  <version>0.1.6</version>
</dependency>
```

### Rust runtime

```bash
cargo add acp-runtime@0.1.6
```

### Go runtime

Available from the public repository:

```bash
go get github.com/beltxa/acp/sdks/go@v0.1.6
```

### Mojo runtime

Mojo support is available in the repository under `sdks/mojo` and is currently experimental. It is not part of the public package publish for this release.

## Examples and demos

Each SDK includes small language-specific examples for first use.

For full cross-language interoperability demos showing ACP agents communicating across languages, see:

```text
/demos
```

## Interoperability layers

ACP is a protocol, not just a library. Its value is in enabling agents implemented in different languages to communicate using the same semantics.

Canonical proof:

- `demos/canonical_interop/`
- `sdks/tests/INTEROPERABILITY_LAYERS.md` (layer model and claim boundaries)

This is the smallest interoperability proof layer and the recommended first evidence path.

Extended walkthroughs:

- `demos/` (non-canonical, larger scenarios)

Showcase applications:

- `tools/chess-player`
- `tools/poker-demo`

Showcase apps are not the protocol contract source of truth and not the parity benchmark.

## Repo Structure

- `getting-started/`: verified local ping flow
- `examples/`: runnable demos (`hello_world_agent.py`, one-to-one, one-to-many, capabilities)
- `sdks/`: language SDK implementations
- `demos/`: interoperability proof assets (`canonical_interop` + extended walkthroughs)
- `tools/`: showcase applications (chess/poker and other domain-rich demos)
- `cli/`: ACP CLI (`acp`)
- `relay-dev/`: developer relay for local/test routing

## Open Source Scope

This repository is for learning, local development, and interoperability testing.

---

## 5-minute success path: send a local ping

From repository root:

```bash
./getting-started/quickstart_ping.sh
```

Expected output:

```text
Ping delivered successfully: ['DELIVERED']
# or ['ACKNOWLEDGED']
Quickstart completed in <seconds>s
```

Full walkthrough: `getting-started/README.md`.

## Canonical Hello World (single-file demo)

`ACP-A1` and `ACP-A9` are implemented as one canonical example:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e sdks/python
python examples/hello_world_agent.py
```

Example output:

```json
{
  "agent_id": "agent:hello.world@localhost:9012",
  "capability_ping": true
}
```

## Direct vs Relay

Direct delivery:

```text
Sender Agent  ->  Recipient Agent
```

Relay delivery:

```text
Sender Agent  ->  Relay  ->  Recipient Agent
```

- `direct`: use when recipients are reachable at known endpoints.
- `relay`: use when recipients are temporarily offline or network-restricted.
- `auto`: SDK tries direct first, then falls back to relay when available.

## Simplified Real ACP Message Envelope

```json
{
  "envelope": {
    "acp_version": "1.0",
    "message_class": "SEND",
    "message_id": "c6b9af4d-6c9b-4bb6-a6f0-7e2cf90d5a59",
    "operation_id": "62cc4f5a-4df8-47c4-b6da-552887ba18c8",
    "timestamp": "2026-03-17T16:00:00Z",
    "expires_at": "2026-03-17T16:05:00Z",
    "sender": "agent:sender.bot@localhost:9010",
    "recipients": ["agent:receiver.bot@localhost:9011"],
    "context_id": "quickstart-ping",
    "crypto_suite": "ACP-AES256-GCM+X25519+ED25519"
  },
  "protected": {
    "nonce": "<base64>",
    "ciphertext": "<base64>",
    "wrapped_content_keys": [
      {
        "recipient": "agent:receiver.bot@localhost:9011",
        "ephemeral_public_key": "<base64>",
        "nonce": "<base64>",
        "ciphertext": "<base64>"
      }
    ],
    "payload_hash": "<sha256-hex>",
    "signature_kid": "did:acp:sender.bot@localhost:9010#key-1",
    "signature": "<base64>"
  }
}
```

The decrypted application payload can be as simple as:

```json
{
  "type": "request",
  "capability": "ping",
  "payload": {
    "message": "hello"
  }
}
```


## License

Apache License 2.0.

## Change Log

### v0.1.0
 Initial release - Unstable
### v0.1.1
 Stable code
### v0.1.2
  Introduced concept of "tenant" to allow differentiation of multiple agents with the same name
### v0.1.3 
   Renamed "tenant" to "namespace" for clarity. Added transport authentication specifications
