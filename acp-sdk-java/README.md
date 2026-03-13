# ACP Java SDK (Minimal)

This module provides a minimal Java ACP SDK client designed to interoperate with the Python reference implementation.

## Scope

- identity load/create with signed identity documents
- ACP envelope/protected payload models
- `SEND`, `ACK`, `FAIL` message handling (plus `CAPABILITIES` and `COMPENSATE` structures)
- Ed25519 signatures, X25519 wrapping, AES-256-GCM payload encryption
- direct HTTP, relay HTTP, and AMQP 0-9-1 send (RabbitMQ-compatible)
- AMQP queue/exchange conventions:
  - exchange: `acp.exchange`
  - queue: `acp.agent.<agent_identifier>`
  - routing key: `agent.<agent_identifier>`
- lightweight deduplication by `message_id`

## Build

```bash
mvn test
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
