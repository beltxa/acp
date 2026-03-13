
# ACP Relay Architecture Decision Note
## Decision: Stateless-by-Default Relay Model

### Status
Accepted (ACP Draft Architecture)

### Context

ACP relays are intermediary nodes used to route messages between agents when direct communication is not possible.
During protocol design two main relay models were considered:

1. Stateful Relay Model
2. Stateless Relay Model

Stateful relays maintain persistent delivery state such as message queues, acknowledgement tracking, retry scheduling, and buffering for offline recipients.

Stateless relays simply validate envelopes and forward messages without maintaining durable state.

The ACP protocol also supports multi-recipient messaging and allows multiple routing paths across a relay network.

### Problem

ACP must balance several competing goals:

- low friction adoption
- decentralized network growth
- strong security guarantees
- enterprise compatibility
- operational simplicity
- resilience across distributed systems

A fully stateful relay network would resemble traditional messaging middleware and create higher operational complexity.
A purely stateless network shifts delivery responsibility to agents but improves resilience and ease of deployment.

### Decision

ACP adopts a stateless-by-default relay architecture.

Key principles:

- ACP relays should not maintain durable message delivery state by default
- Message routing should be best-effort and forward-only
- Agents and SDKs must handle retries, deduplication, and delivery reconciliation
- ACP delivery semantics are at-least-once
- Recipients must deduplicate messages using `message_id`
- Multiple relay paths between agents are permitted

### Consequences

Advantages:

- simpler relay implementation
- easier community adoption
- lower infrastructure cost
- improved network resilience through multi-path routing
- reduced trust requirements for relay operators

Trade-offs:

- delivery guarantees must be handled by agents or higher-level infrastructure
- offline message storage is not guaranteed by default
- some applications may require stronger guarantees

### Enterprise Extension

Organizations may deploy stateful relay profiles that support:

- durable store-and-forward
- delivery tracking
- retry scheduling
- operational monitoring
- compliance logging

These features are considered optional deployment profiles, not core ACP protocol requirements.

### Summary

ACP relays are:

- stateless by default
- message routers rather than message brokers
- capable of multi-path routing
- compatible with optional stateful enterprise relay implementations
