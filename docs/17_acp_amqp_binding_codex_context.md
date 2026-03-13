
# ACP AMQP Binding – Codex Context Prompt

You are implementing the AMQP transport binding for the Agent Communication Protocol (ACP).

ACP is a secure, transport‑agnostic protocol used by autonomous agents to communicate.

The AMQP binding allows ACP messages to travel through AMQP brokers such as RabbitMQ.

---

## Implementation Objective

Create an AMQP transport adapter that enables:

- ACP agents to publish messages to AMQP
- ACP agents to receive messages from AMQP
- interoperability with the Python ACP SDK and Java ACP client

The AMQP binding must not change the ACP protocol.

---

## Core Rules

1. ACP message structure remains unchanged.
2. AMQP message body contains the serialized ACP message.
3. AMQP headers may mirror ACP metadata but are not canonical.
4. Broker must never decrypt payloads.
5. Delivery semantics remain at‑least‑once.
6. Recipients deduplicate using message_id.

---

## Required Components

Codex should produce:

### 1. AMQP Transport Adapter (Python)

Example module:

acp.transport.amqp

Responsibilities:

- connect to AMQP broker
- publish ACP messages
- subscribe to agent queue
- deliver ACP envelope to SDK message handler

---

### 2. AMQP Routing Model

Exchange:

acp.exchange

Routing key:

agent.<agent_identifier>

Queues:

acp.agent.<agent_identifier>

Queue bindings should match routing keys.

---

### 3. Multi‑Recipient Messaging

For SEND with multiple recipients:

for each recipient:
    publish AMQP message with routing key

---

### 4. Consumer Flow

Upon receiving a message:

1. Parse ACP envelope
2. Verify signature
3. Decrypt payload
4. Process message
5. Send ACK or FAIL

---

## Out of Scope

Do not implement:

- event channels
- enterprise premium profile
- blockchain
- exactly-once semantics
- advanced broker transactions

---

## Testing Requirements

Codex should provide tests demonstrating:

1. Python agent sending message through RabbitMQ
2. Java agent receiving through AMQP
3. Multi-recipient delivery via AMQP
4. Duplicate delivery tolerance
5. ACK and FAIL message flow

---

## Goal

Agents using ACP should be able to communicate through AMQP exactly as they do through HTTP or relay transport.

AMQP acts purely as a transport binding, not as a new protocol layer.
