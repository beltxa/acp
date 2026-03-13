
# ACP Identity – Short Design Specification

## Overview

ACP identity provides a decentralized mechanism to authenticate agents and enable encrypted communication.

Each ACP agent possesses:

- a unique identifier
- cryptographic key pairs
- a signed identity document
- optional trust proofs

---

## Identity Syntax

Agent identifiers follow the format:

agent:<name>@<domain>

Examples:

agent:inventory.bot@companyA.com  
agent:research.agent@labX.org

Local development identities may omit domains.

---

## Identity Document

Each identity publishes a signed document containing:

- agent identifier
- signing keys
- encryption keys
- endpoint or relay hints
- trust profile
- validity window
- optional verification proofs

---

## Discovery Rules

Agent identity documents may be resolved via:

1. Local cache
2. Domain resolution (.well-known/acp-agent)
3. Relay registry
4. Enterprise identity directory

---

## Trust Profiles

ACP supports progressive trust levels:

self_asserted  
domain_verified  
enterprise_managed  
regulated_assured

---

## Key Management

ACP identities include:

- signing keys for message authentication
- encryption keys for secure payload delivery

Keys support:

- rotation
- expiration
- revocation metadata

---

## SDK Example

Example minimal SDK interaction:

```python
from acp import Agent

agent = Agent.create("agent:inventory.bot@companyA.com")

agent.send(
    recipients=["agent:shipping.bot@companyB.com"],
    payload={"task": "ship_order"},
    context="order-123"
)
```

The SDK handles:

- key generation
- encryption
- signing
- message routing
- identity document creation

---

## Design Goal

ACP identity should enable secure communication between agents while remaining simple enough for rapid adoption across developer ecosystems.
