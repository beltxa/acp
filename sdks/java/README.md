# ACP Java SDK (Minimal)

This module provides a minimal Java ACP SDK client designed to interoperate with the Python reference implementation.

## Scope

- identity load/create with signed identity documents
- ACP envelope/protected payload models
- `SEND`, `ACK`, `FAIL` message handling (plus `CAPABILITIES` and `COMPENSATE` structures)
- Ed25519 signatures, X25519 wrapping, AES-256-GCM payload encryption
- direct HTTP, relay HTTP, AMQP 0-9-1, and MQTT 5 transport send/consume
- AMQP queue/exchange conventions:
  - exchange: `acp.exchange`
  - queue: `acp.agent.<agent_identifier>`
  - routing key: `agent.<agent_identifier>`
- MQTT topic conventions:
  - topic prefix: `acp/agent`
  - topic: `acp/agent/<normalized_agent_identifier>`
  - default QoS: `1` (at-least-once)
- lightweight deduplication by `message_id`

## Build

```bash
mvn test
```

## Maven Coordinates

```xml
<dependency>
  <groupId>io.acp</groupId>
  <artifactId>acp-sdk</artifactId>
  <version>0.1.0</version>
</dependency>
```

## Example

```java
AcpAgent agent = AcpAgent.loadOrCreate("agent:dealer@poker.demo");

SendResult result = agent.send(
    List.of("agent:player1@poker.demo", "agent:player2@poker.demo"),
    Map.of("type", "hand_start", "hand_id", "123"),
    "hand-123"
);
```

## Overlay Adapters (HTTP)

The SDK includes a first overlay pass for incremental ACP adoption on existing HTTP services:

- `OverlayInboundAdapter`: wraps inbound request handling and delegates ACP verification/decryption to `AcpAgent`.
- `OverlayOutboundAdapter`: wraps outbound business payload sends and can bootstrap target metadata from `/.well-known/acp`.

Both adapters are thin wrappers and reuse the existing ACP runtime logic.

Framework-friendly runtime wrapper:

- `org.acp.client.framework.OverlayHttpRuntime`

This wrapper is designed for Spring/servlet controller integration:

- inbound ACP-over-HTTP handling (`handleMessageBody`)
- inbound convenience aliases (`handle`, static `handle(..., OverlayConfig)`)
- `/.well-known/acp` and identity payload helpers
- outbound ACP-over-HTTP send helper with well-known bootstrap (`sendBusinessPayload`, `sendAcp`)
- well-known cache-control helper (`wellKnownHeaders`)
